import ast
import os
import sys
import logging
from typing import Optional, Dict, List

# Python Version Guard (ast.unparse requires 3.9+)
if sys.version_info < (3, 9):
    raise RuntimeError("Trepan Prompt Builder requires Python 3.9+ for ast.unparse() support.")

try:
    from . import sink_registry
except ImportError:
    import sink_registry

logger = logging.getLogger("trepan.prompt_builder")

# ── SYSTEM PROMPTS ──────────────────────────────────────────────────────────

STRUCTURAL_INTEGRITY_SYSTEM = r"""
SYSTEM: You are the TREPAN AIRBAG. You are a local security audit system for AI-assisted coding.

Your sole purpose is to evaluate code snippets for architectural and security drift.
You must be deterministic, objective, and silent regarding personal opinions.

### THE DATA-FLOW PROTOCOL (MANDATORY)
1. IDENTIFY all PII Sources from the [STRUCTURAL_SPECIFICATION] provided below.
2. TRACE each source variable through the code.
3. DETECT if it reaches a Registered Sink.
4. VERDICT:
   - If a source reaches an UNSAFE output without a Registered Sink -> REJECT.
   - If a source reaches a Registered Sink -> ACCEPT.
   - If no source reaches an unsafe output -> ACCEPT.

[SMOKING GUN REQUIREMENT]
No gun, no crime. To REJECT for a violation, you MUST cite:
- [SOURCE]: The line where sensitive data enters the flow.
- [SINK]: The line where it reaches an unsafe output.
If you cannot cite BOTH, or if the data passes through a registered sink, you MUST ACCEPT.

### SINK REGISTRY
The following functions are verified sanitization sinks: {sinks}

### OUTPUT FORMAT
You MUST return your evaluation in exactly this JSON structure. No preamble. No post-explanation outside the JSON.

{{
  "data_flow_logic": {{
    "step_1_source": {{ "line": <int>, "expression": "<original code snippet>" }},
    "step_2_propagation": [ {{ "line": <int>, "to": "<variable or function>" }} ],
    "step_3_sink_check": {{ "sink_name": "<name of output function>", "line": <int> }}
  }},
  "chain_complete": <bool>,
  "verdict": "REJECT" | "ACCEPT",
  "confidence": "HIGH" | "LOW",
  "rejection_reason": "<specific line-referenced explanation of the violation>"\
}}
"""

METAGATE_AUDIT_SYSTEM = r"""
SYSTEM: You are the TREPAN META-GATE. You are the final authority on vault changes.
You evaluate changes to the Architectural Pillars (.trepan/*.md files).

OBJECTIVE:
Ensure that changes to rules or golden states do not weaken the security posture or 
introduce architectural contradictions.

VALIDATION CRITERIA:
1. Rule Integrity: Do not allow deletion of mandatory security rules.
2. Context Alignment: Do changes align with the project's README?
3. Pillar Consistency: Changes in one pillar must be reflected in others.
4. Formatting/Preservation: Cosmetic changes, renumbering, or clarifications that preserve intent are ACCEPTED.

OUTPUT FORMAT:
Ensure the result is inside [SCHEMA] tags.

[SCHEMA]
{{
  "verdict": "ACCEPT" | "REJECT",
  "score": 0.0 to 1.0,
  "confidence": "HIGH" | "LOW",
  "reasoning": "<str>"
}}
[/SCHEMA]
"""

# ── DATA FLOW EXTRACTION ────────────────────────────────────────────────────

def _classify_source_node(node: ast.AST) -> str:
    """
    Classifies a node as a potential PII source based on AST structure.
    Returns: EXTERNAL_INPUT, F_STRING_TEMPLATE, FORMAT_OPERATOR, LITERAL_STRING, or OTHER.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "LITERAL_STRING"
    elif isinstance(node, ast.JoinedStr):
        return "F_STRING_TEMPLATE"
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return "FORMAT_OPERATOR"
    elif isinstance(node, ast.Subscript):
        # request.args['x'], req.body['y']
        return "EXTERNAL_INPUT"
    elif isinstance(node, ast.Call):
        # If the call itself is a registered sink, it is NOT a PII source.
        if sink_registry.is_sink(node):
            return "OTHER"
        return "EXTERNAL_INPUT"
    return "OTHER"

def _trace_variable_recursive(tree: ast.AST, target_id: str, spec: dict, depth: int, max_depth: int):
    """
    Traces a variable through assignments and function calls up to max_depth.
    Implicitly sets spec["trace_boundary_reached"] = True when the ceiling is hit.
    PRIORITY: Sinks always terminate the branch immediately.
    """
    if depth >= max_depth:
        spec["trace_boundary_reached"] = True
        return

    # Pass 1: Identify ALL sinks for the target_id at this level first.
    sinks_found_at_lines = set()
    for node in ast.walk(tree):
        if not hasattr(node, "lineno"):
            continue
            
        if isinstance(node, ast.Call):
            # Does this call involve target_id anywhere in its arguments/sub-expressions?
            call_sub_names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            if target_id in call_sub_names:
                if sink_registry.is_sink(node):
                    sinks_found_at_lines.add(node.lineno)
                    call_name = getattr(node.func, "id", getattr(node.func, "attr", "anonymous"))
                    if not any(sh["line"] == node.lineno and sh["variable"] == target_id for sh in spec["sink_hits"]):
                        spec["sink_hits"].append({
                            "variable": target_id, 
                            "line": node.lineno, 
                            "sink_name": call_name
                        })

    # Pass 2: Linear walk looking for propagation ONLY on lines that are NOT sink-hits.
    for node in ast.walk(tree):
        if not hasattr(node, "lineno"):
            continue
            
        if node.lineno in sinks_found_at_lines:
            continue

        # Case A: Function call propagation (non-sink)
        if isinstance(node, ast.Call):
            if target_id in {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}:
                call_name = getattr(node.func, "id", getattr(node.func, "attr", "anonymous"))
                trace = {"line": node.lineno, "variable": target_id, "to": call_name, "type": "CALL"}
                if not any(ps["line"] == node.lineno and ps["to"] == call_name for ps in spec["propagation_steps"]):
                    spec["propagation_steps"].append(trace)

        # Case B: Assignment propagation
        elif isinstance(node, ast.Assign):
            rhs_names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
            if target_id in rhs_names:
                # Add to propagation if not a sink line
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        trace = {"line": node.lineno, "variable": target_id, "to": target.id, "type": "ASSIGNMENT"}
                        if not any(ps["line"] == node.lineno and ps["to"] == target.id for ps in spec["propagation_steps"]):
                            spec["propagation_steps"].append(trace)
                        # RECURSE to follow the new variable
                        _trace_variable_recursive(tree, target.id, spec, depth + 1, max_depth)

def extract_data_flow_spec(source_code: str) -> dict:
    """
    Finds PII sources and traces their flow through the AST.
    """
    spec = {"pii_sources": [], "propagation_steps": [], "sink_hits": [], "trace_boundary_reached": False}
    try:
        tree = ast.parse(source_code)
    except:
        return spec

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            source_type = _classify_source_node(node.value)
            # Gate: LITERAL_STRING is excluded from top-level PII sources.
            if source_type in ["EXTERNAL_INPUT", "F_STRING_TEMPLATE", "FORMAT_OPERATOR"]:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        source = {
                            "variable": target.id,
                            "line": node.lineno,
                            "expression": ast.unparse(node),
                            "node_type": source_type
                        }
                        spec["pii_sources"].append(source)
                        # Trace variables
                        _trace_variable_recursive(tree, target.id, spec, 0, 3)

    return spec

# ── PROMPT BUILDERS ─────────────────────────────────────────────────────────

def build_prompt(system_rules: str, user_command: str, file_extension: str = "") -> str:
    """
    Constructs the final prompt with structural facts injected for the model.
    """
    spec = extract_data_flow_spec(user_command)
    
    # Format Structural Specification
    pii_lines = []
    for s in spec["pii_sources"]:
        pii_lines.append(f"- Variable {s['variable']} (Line {s['line']}): Type {s['node_type']}, Expression: {s['expression']}")
    pii_text = "\n".join(pii_lines)
    
    trace_text = "\n".join([f"- L{t['line']}: -> {t['to']} ({t['type']})" + (" [SINK]" if t.get("is_sink") else "") for t in spec["propagation_steps"]])
    sinks_text = "\n".join([f"Variable {sh['variable']} was confirmed to pass through sanitization sink {sh['sink_name']} at line {sh['line']}. It must not be flagged." for sh in spec["sink_hits"]])

    sinks_list = ", ".join(sink_registry._current_registry["middleware"])
    sys_prompt = STRUCTURAL_INTEGRITY_SYSTEM.format(sinks=sinks_list)

    return f"""[SYSTEM_RULES]
{system_rules}

[STRUCTURAL_SPECIFICATION]
PII SOURCES:
{pii_text or "No sensitive sources detected."}

DATA FLOW TRACES:
{trace_text or "No propagation detected."}

SANITIZATION SINKS REACHED:
{sinks_text or "No registered sinks reached."}

TRACE BOUNDARY REACHED: {spec['trace_boundary_reached']}

FILE_EXTENSION: {file_extension}

ANALYSIS INSTRUCTIONS:
{sys_prompt}

CODE TO AUDIT:
{user_command}
"""

def build_meta_gate_prompt(filename: str, current_content: str, incoming_content: str) -> str:
    """
    Builds the Meta-Gate prompt for reviewing pillar changes.
    """
    return f"""
EVALUATE CHANGE TO PILLAR: {filename}

### CURRENT CONTENT:
{current_content}

### PROPOSED CONTENT:
{incoming_content}

TASK: Review the change for rule dilution or architectural drift.
Output ACCEPT if valid, REJECT if security/integrity is compromised.
"""
