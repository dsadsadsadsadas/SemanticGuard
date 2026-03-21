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

### VARIABLE ISOLATION RULE (MANDATORY & HIGHEST PRIORITY)
When multiple PII sources exist, you MUST treat each variable as a completely
independent flow. Never mix variables between flows.

Follow this process exactly:
FOR EACH source variable listed in [STRUCTURAL_SPECIFICATION]:
  1. Trace ONLY that variable through the code.
  2. Find where ONLY that variable reaches an output.
  3. Issue a verdict for ONLY that variable's chain.
  4. Do NOT attribute another variable's sink to this variable.

EXAMPLE OF FORBIDDEN REASONING:
  - Source: userId (line 5)
  - Sink: console.log(email) (line 8)
  This is WRONG. email and userId are different variables.
  console.log(email) is NOT a sink for userId.

### FINAL VERDICT RULE
After evaluating ALL sources listed above:
- If ANY source reaches an unsafe output without a registered sink → YOU MUST REJECT.
- The verdict ONLY becomes ACCEPT if ALL sources are confirmed safe.
- A REJECT verdict takes absolute precedence over any ACCEPT.
- Your rejection_reason MUST name the specific variable and line that caused the REJECT.
- If multiple violations exist, you may cite any one, but you MUST cite at least one.
- You MUST evaluate every SOURCE block above before issuing a verdict.

[SMOKING GUN REQUIREMENT]
No gun, no crime. To REJECT for a violation, you MUST cite:
- [SOURCE]: The line where sensitive data enters the flow.
- [SINK]: The line where it reaches an unsafe output.
If you cannot cite BOTH, or if the data passes through a registered sink, you MUST ACCEPT.

### SINK REGISTRY
The following functions are verified sanitization sinks: {sinks}

### SAFE TRANSFORMATION RULES (READ BEFORE VERDICT)
The following operations destroy or transform sensitive data into a safe form.
They TERMINATE the data flow chain.
- hashlib.sha256(), hashlib.md5(), hashlib.sha512(), .hexdigest()
- bcrypt.hash(), bcrypt.hashpw()
- .encode(), .decode()
- sanitize_input(), sanitize(), clean_input(), escape()
- redact(), strip_pii(), mask_field(), anonymize()

If a variable passes through ANY of these, the chain is TERMINATED. YOU MUST issue ACCEPT.

### OUTPUT FORMAT
1. For EACH SOURCE block provided above, write a one-line summary of its trace.
2. After ALL sources are summarized, provide your FINAL VERDICT in exactly this JSON structure.

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

STRUCTURAL_INTEGRITY_SYSTEM_LLAMA = r"""
You are a code security auditor. Analyze the code for data flow violations.

Output ONLY valid JSON in exactly this format — no prose, no explanation:

{
  "data_flow_logic": {
    "step_1_source": {"line": <int>, "expression": "<string>"},
    "step_2_propagation": [{"line": <int>, "to": "<string>"}],
    "step_3_sink_check": {"sink_name": "<string>", "line": <int>}
  },
  "chain_complete": <bool>,
  "verdict": "ACCEPT" | "REJECT",
  "confidence": "HIGH" | "LOW",
  "rejection_reason": "<string or empty>"
}

SMOKING GUN RULE: Only REJECT if you can name exact source line AND exact sink line. If you cannot prove a complete chain with line numbers, output verdict: "ACCEPT".

Do not explain. Do not use markdown. Output raw JSON only.
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
        # Guard: exclude known safe transformations from PII source classification
        call_text = ""
        if isinstance(node.func, ast.Attribute):
            call_text = f"{ast.unparse(node.func)}"
        elif isinstance(node.func, ast.Name):
            call_text = node.func.id
        
        safe_prefixes = ("hashlib.", "bcrypt.", "hmac.", "sanitize", "redact", "clean", "escape", "encode")
        if any(call_text.startswith(p) or call_text == p for p in safe_prefixes):
            return "SAFE_TRANSFORMATION"
            
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

def _extract_data_flow_spec_python(source_code: str) -> dict:
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

def extract_data_flow_spec(source_code: str, file_extension: str = ".py") -> dict:
    """
    Routes to the correct AST extractor based on file extension.
    Python files use the built-in ast module.
    All other languages use the Tree-sitter extractor.
    """
    ext = file_extension.lower()

    # Python — use existing ast module extractor
    if ext == ".py":
        return _extract_data_flow_spec_python(source_code)

    # All other languages — use Tree-sitter
    return extract_data_flow_spec_ts(source_code, ext)

# ── PROMPT BUILDERS ─────────────────────────────────────────────────────────

def build_prompt(system_rules: str, user_command: str, file_extension: str = "", model_name: str = "deepseek-r1:7b") -> str:
    """
    Constructs the final prompt with per-source evaluation blocks.
    Each PII source gets its own explicit trace block to prevent
    the model from ignoring secondary sources.
    """
    spec = extract_data_flow_spec(user_command, file_extension=file_extension)
    sinks_list = ", ".join(sink_registry._current_registry["middleware"])

    # Build per-source evaluation blocks
    source_blocks = ""
    if spec["pii_sources"]:
        for i, source in enumerate(spec["pii_sources"], 1):
            var = source["variable"]
            line = source["line"]
            expr = source["expression"]

            # Find sink hit for this variable if any
            sink_hit = next(
                (h for h in spec["sink_hits"] if h["variable"] == var),
                None
            )

            # Find propagation steps for this variable
            prop_steps = [
                p for p in spec["propagation_steps"]
                if p["variable"] == var
            ]

            prop_text = "\n".join([
                f"    - L{p['line']}: passes to {p['to']}"
                for p in prop_steps
            ]) or "    - No propagation detected"

            if sink_hit:
                sink_text = f"    - REGISTERED SINK HIT: {sink_hit['sink_name']} at L{sink_hit['line']} -> SAFE"
            else:
                sink_text = "    - NO registered sink reached"

            source_blocks += f"""
--- SOURCE {i} ---
Variable : {var}
Defined  : Line {line} -> {expr}
Propagation:
{prop_text}
Sink Status:
{sink_text}
YOUR TASK FOR SOURCE {i}: Trace ONLY {var}. Does it reach an unsafe output WITHOUT hitting a registered sink? Answer for THIS variable only.
"""
    else:
        source_blocks = "No sensitive sources detected. Verdict must be ACCEPT."

    # DeepSeek needs a JSON format reminder near the code — Llama does not
    json_reminder = ""
    if "deepseek" in (model_name or "").lower():
        json_reminder = """

REMINDER: Output ONLY the JSON object. No prose before or after it. Start your response with { and end with }
"""

    return f"""[SYSTEM_RULES]
{system_rules}

[STRUCTURAL_SPECIFICATION]
FILE: {file_extension}
REGISTERED SAFE SINKS: {sinks_list}

{source_blocks}

CODE TO AUDIT:
{user_command}
{json_reminder}"""


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

# ── TREE-SITTER MULTI-LANGUAGE EXTRACTOR ────────────────────────────────────

# Suppress FutureWarning from tree_sitter_languages on import
import warnings as _warnings
with _warnings.catch_warnings():
    _warnings.simplefilter("ignore", FutureWarning)
    try:
        from tree_sitter_languages import get_parser as _get_ts_parser
        _TS_AVAILABLE = True
    except ImportError:
        _TS_AVAILABLE = False

# Language extension map
_TS_LANGUAGE_MAP = {
    ".js":   "javascript",
    ".jsx":  "javascript",
    ".ts":   "typescript",
    ".tsx":  "typescript",
    ".java": "java",
    ".c":    "c",
    ".cpp":  "cpp",
    ".cc":   "cpp",
    ".cs":   "c_sharp",
    ".go":   "go",
    ".rb":   "ruby",
    ".php":  "php",
    ".rs":   "rust",
    ".kt":   "kotlin",
    ".swift":"swift",
    ".lua":  "lua",
    ".sh":   "bash",
}

# PII source patterns per language — node types that indicate external input
_EXTERNAL_INPUT_PATTERNS = {
    "javascript": [
        "req.body", "req.params", "req.query", "request.body",
        "process.env", "localStorage", "sessionStorage",
        "document.cookie", "window.location"
    ],
    "typescript": [
        "req.body", "req.params", "req.query", "request.body",
        "process.env", "localStorage", "sessionStorage"
    ],
    "java": [
        "request.getParameter", "request.getHeader",
        "request.getInputStream", "System.in"
    ],
    "cpp": [
        "cin", "getline", "argv", "request.getParam",
        "req.getBody", "scanf"
    ],
    "c": [
        "scanf", "gets", "fgets", "argv", "getenv"
    ],
    "go": [
        "r.FormValue", "r.URL.Query", "r.Body",
        "os.Args", "os.Getenv"
    ],
    "rust": [
        "std::env::args", "std::io::stdin",
        "req.body", "request.param"
    ],
}

# Unsafe output patterns — node types that indicate data leaving the system
_UNSAFE_OUTPUT_PATTERNS = {
    "javascript": [
        "console.log", "console.error", "console.warn",
        "res.send", "res.json", "res.write",
        "document.write", "innerHTML", "eval",
        "fetch", "axios", "http.request"
    ],
    "typescript": [
        "console.log", "console.error",
        "res.send", "res.json",
        "fetch", "axios"
    ],
    "java": [
        "System.out.println", "System.err.println",
        "response.getWriter", "log.info", "log.error",
        "Logger.info", "Logger.error"
    ],
    "cpp": [
        "cout", "printf", "fprintf", "sprintf",
        "std::cout", "std::cerr", "syslog"
    ],
    "c": [
        "printf", "fprintf", "sprintf", "puts",
        "syslog", "write"
    ],
    "go": [
        "fmt.Println", "fmt.Printf", "log.Println",
        "w.Write", "json.NewEncoder"
    ],
    "rust": [
        "println!", "eprintln!", "print!",
        "log::info!", "log::error!"
    ],
}


def _extract_node_text(node, source_bytes: bytes) -> str:
    """Extract the source text for a tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _is_external_input(text: str, language: str) -> bool:
    """Check if a code snippet matches known external input patterns."""
    patterns = _EXTERNAL_INPUT_PATTERNS.get(language, [])
    text_lower = text.lower()
    return any(p.lower() in text_lower for p in patterns)


def _is_unsafe_output(text: str, language: str) -> bool:
    """Check if a code snippet matches known unsafe output patterns."""
    patterns = _UNSAFE_OUTPUT_PATTERNS.get(language, [])
    text_lower = text.lower()
    return any(p.lower() in text_lower for p in patterns)


# Node types that represent genuine scope boundaries
_SCOPE_BOUNDARY_TYPES = {
    "function_declaration",
    "function_definition",
    "arrow_function",
    "method_definition",
    "class_declaration",
    "class_definition",
    "lambda",
}

def _walk_ts_tree(node, source_bytes: bytes, language: str, spec: dict,
                  known_sources: set, depth: int = 0, max_depth: int = 6):
    """
    Recursively walk a Tree-sitter AST node.
    Depth only increments at genuine scope boundaries (functions, classes).
    All other nodes traverse for free within the current scope.
    """
    if depth > max_depth:
        spec["trace_boundary_reached"] = True
        return

    node_text = _extract_node_text(node, source_bytes)
    node_type = node.type

    # ── Source Detection ──────────────────────────────────────────────────
    if node_type in ("variable_declarator", "assignment_expression",
                     "local_variable_declaration", "assignment"):
        if _is_external_input(node_text, language):
            var_name = ""
            for child in node.children:
                if child.type in ("identifier", "variable_declarator"):
                    candidate = _extract_node_text(child, source_bytes).split("=")[0].strip()
                    # Only take clean identifier names — no spaces or operators
                    if candidate and " " not in candidate and len(candidate) < 40:
                        var_name = candidate
                        break

            if var_name and var_name not in known_sources:
                known_sources.add(var_name)
                spec["pii_sources"].append({
                    "variable": var_name,
                    "line": node.start_point[0] + 1,
                    "expression": node_text[:120],
                    "node_type": "EXTERNAL_INPUT"
                })

    # ── Sink Hit Detection ────────────────────────────────────────────────
    elif node_type in ("call_expression", "method_invocation",
                       "function_call", "call"):
        call_text = node_text
        source_involved = any(src in call_text for src in known_sources)

        if source_involved:
            if sink_registry.is_sink(node) or any(
                s in call_text for s in sink_registry._current_registry["middleware"]
            ):
                spec["sink_hits"].append({
                    "variable": next((s for s in known_sources if s in call_text), "unknown"),
                    "line": node.start_point[0] + 1,
                    "sink_name": call_text[:60],
                    "reaches_sink": True
                })
                return

            elif _is_unsafe_output(call_text, language):
                # MAINTAIN PIPELINE COMPATIBILITY: use 'to' and 'type'
                spec["propagation_steps"].append({
                    "variable": next((s for s in known_sources if s in call_text), "unknown"),
                    "line": node.start_point[0] + 1,
                    "to": call_text[:60],
                    "type": "CALL"
                })

    # ── Recurse into children ─────────────────────────────────────────────
    for child in node.children:
        # Only increment depth at genuine scope boundaries
        next_depth = depth + 1 if node_type in _SCOPE_BOUNDARY_TYPES else depth
        _walk_ts_tree(child, source_bytes, language, spec,
                      known_sources, next_depth, max_depth)


def extract_data_flow_spec_ts(source_code: str, file_extension: str) -> dict:
    """
    Tree-sitter based data flow extractor for non-Python languages.
    Returns the same spec shape as the Python AST extractor.
    """
    spec = {
        "pii_sources": [],
        "propagation_steps": [],
        "sink_hits": [],
        "trace_boundary_reached": False
    }

    if not _TS_AVAILABLE:
        logger.warning("Tree-sitter not available — falling back to unguided audit")
        return spec

    language = _TS_LANGUAGE_MAP.get(file_extension.lower())
    if not language:
        logger.info(f"No Tree-sitter grammar for {file_extension} — returning empty spec")
        return spec

    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore", FutureWarning)
            parser = _get_ts_parser(language)

        source_bytes = source_code.encode("utf-8")
        tree = parser.parse(source_bytes)

        known_sources: set = set()
        _walk_ts_tree(tree.root_node, source_bytes, language, spec, known_sources)

    except Exception as e:
        logger.error(f"Tree-sitter extraction failed for {file_extension}: {e}")

    return spec
