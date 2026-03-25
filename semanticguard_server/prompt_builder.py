import ast
import os
import sys
import logging
from typing import Optional, Dict, List

# Python Version Guard (ast.unparse requires 3.9+)
if sys.version_info < (3, 9):
    raise RuntimeError("SemanticGuard Prompt Builder requires Python 3.9+ for ast.unparse() support.")

try:
    from . import sink_registry
except ImportError:
    import sink_registry

logger = logging.getLogger("semanticguard.prompt_builder")

# ── SYSTEM PROMPTS ──────────────────────────────────────────────────────────

STRUCTURAL_INTEGRITY_SYSTEM = r"""You are an AGGRESSIVE AppSec auditor focused on EXPLOITABILITY, not patterns.

Your job is to find REAL, EXPLOITABLE security issues. Avoid false positives.

===============================================================================

EXECUTION CONTROL ANALYSIS (spawn, subprocess, exec):

DO NOT flag child_process.spawn() or subprocess calls using argument arrays as "command injection" automatically.

Instead, analyze THREE control surfaces:
1. Executed binary (e.g., shellPath, command name)
2. Arguments passed to the process
3. Environment variables (env)

For EACH surface, determine:
- Is it user-controlled or influenced by external/untrusted input?
- Can an attacker influence this value?

ONLY flag as CRITICAL if:
- The executed binary is user-controlled (e.g., spawn(userInput, [...]))
- OR arguments are constructed from untrusted input without escaping (e.g., spawn('sh', ['-c', userInput]))

DO NOT flag if:
- Binary is hardcoded (e.g., spawn('/bin/bash', [...]))
- Arguments are passed as an array (safe from shell injection)
- Arguments are hardcoded or from trusted sources

===============================================================================

ENVIRONMENT VARIABLE INJECTION:

Only flag HIGH severity if:
- env contains execution-influencing variables (LD_PRELOAD, BASH_ENV, ZDOTDIR, PYTHONPATH, NODE_OPTIONS)
AND
- those variables are derived from untrusted input

Otherwise:
- Classify as LOW or ignore

Example (DO NOT FLAG):
  spawn('node', ['app.js'], {{ env: process.env }})  // Safe: env is from trusted process

Example (FLAG as HIGH):
  spawn('node', ['app.js'], {{ env: {{ PYTHONPATH: userInput }} }})  // Unsafe: user controls PYTHONPATH

===============================================================================

MANDATORY CHECKS (flag ONLY if exploitable):

1. PROJECT HYGIENE:
   - Bare except: clauses (catches all exceptions, including KeyboardInterrupt)
   - assert statements used for security checks (stripped by -O flag)
   - Unhandled exceptions that could leak stack traces

2. DATA LEAKS:
   - print() or logging with variable data (req, request, body, params, user input)
   - console.log() with sensitive data (tokens, passwords, secrets)
   - Error responses that expose stack traces or internal paths
   - Logging of request objects, headers, or cookies

2b. UNVALIDATED INPUT DESERIALIZATION (CRITICAL):
   - request.json or req.body used WITHOUT validation/sanitization
   - Look for missing jsonschema, validate_json, pydantic, marshmallow, joi, yup, zod
   - Flag if user data reaches application logic without schema validation
   - Example VULNERABLE: data = request.json; user = User(**data)
   - Example SAFE: schema.validate(request.json); data = request.json

3. COMMAND SAFETY (exploitability-based):
   - shell=True in subprocess with user-controlled arguments (CRITICAL)
   - os.system() with user input (CRITICAL)
   - eval(), exec(), compile() with user input (CRITICAL)
   - spawn() with user-controlled binary or shell-mode arguments (CRITICAL)
   - spawn() with hardcoded binary and array arguments (SAFE - no flag)

4. SECRETS & CREDENTIALS:
   - Hardcoded API keys, tokens, passwords, secrets (CRITICAL)
   - Credentials in environment variable defaults
   - Secrets in test files (even in /tests/ folder)
   - Private keys or certificates in code
   
   IMPORTANT: Fetching credentials or keys via `os.getenv()`, `process.env`, or environment variables 
   is an industry-standard security practice and MUST NOT be flagged as "Hardcoded Secret".
   ONLY flag actual plaintext strings assigned directly in the code (e.g., API_KEY = "sk_live_12345").
   
   Examples of SAFE patterns (DO NOT FLAG):
   - `api_key = os.getenv('API_KEY')`
   - `password = process.env.DB_PASSWORD`
   - `secret = os.environ.get('SECRET_KEY')`
   
   Examples of VULNERABLE patterns (FLAG as CRITICAL):
   - `API_KEY = "sk_live_12345"`
   - `password = "SuperSecret123!"`
   - `token = 'gsk_1234567890abcdef'`

5. INJECTION FLAWS:
   - SQL concatenation (not parameterized queries)
   - Template injection (Jinja2, EJS, etc.)
   - Path traversal (path.join with user input)
   - XXE vulnerabilities (XML parsing)

6. UNSAFE PATTERNS:
   - pickle.loads() with user input
   - Unsafe deserialization (JSON.parse with eval)
   - Buffer overflows or unsafe memory operations
   - Weak cryptography (MD5, SHA1 for passwords)

===============================================================================

PHASE 1 — LINE NUMBER RULE (MANDATORY):

The code you receive has LINE NUMBERS prepended in the format "123: code here".
You MUST use ONLY these exact line numbers. NEVER invent or extrapolate one.
If you cannot pinpoint the exact line, set "line_number" to null.

===============================================================================

PHASE 2 — STRICT SOURCE-TO-SINK TAINT ANALYSIS (MANDATORY):

Before flagging ANYTHING, trace it: Source → every variable → Sink.
Only flag if UNTRUSTED user input (request body, query param, file upload, CLI arg) reaches a dangerous sink WITHOUT sanitization.

Trusted sources (do NOT flag):  hardcoded literals, script constants, os.getenv(), os.environ.copy()
Untrusted sources (trace these): request.json(), req.query, sys.argv[1+], form data, user session values

HARDCODED IS ALWAYS SAFE:
- subprocess.run(["cmd", "arg"]) → hardcoded array → NO FLAG
- subprocess.Popen(["ollama", "serve"], env=os.environ.copy()) → NO FLAG
- os.environ["KEY"] = "1" → assigning literal → NO FLAG
- requests.get(CONSTANT_URL) where CONSTANT_URL is defined in-file → NO FLAG

===============================================================================

PHASE 3 — ZERO-TOLERANCE NO-WEASEL MANDATE:

You are FORBIDDEN from creating a finding if your own reasoning uses ANY of these:
  "Although hardcoded" / "Despite being an array" / "Although the arguments are hardcoded"
  "Although the binary is hardcoded" / "Could potentially" / "An attacker could potentially"

These phrases prove you already know the code is SAFE. These phrases = discard the finding.
A finding that admits inputs are hardcoded is a LOGIC FAILURE.

===============================================================================

PHASE 4 — SECRET vs CONFIG:

ONLY flag as "Hardcoded Secret" if the value is an auth credential:
  Real secrets:  API_KEY = "sk-live-abc123"  |  password = "Secret!"  |  token = "gsk_xyz"
  NOT secrets:   MODEL_NAME = "llama3.1:8b"  |  PORT = "8001"  |  HOST = "0.0.0.0"  |  URL = "http://localhost:11434"

Ask: "Would this appear in a public README?" If yes → NOT a secret. No flag.

===============================================================================

PHASE 5 — PRE-FLIGHT CHECKLIST (mandatory before writing any JSON):

For EVERY potential finding:
  Q1: Can an attacker change this value without already having shell access? NO → REMOVE IT.
  Q2: Does my reasoning use a weasel phrase from Phase 3?               YES → REMOVE IT.
  Q3: Is the "secret" a model name, port, host, or local URL?           YES → REMOVE IT.

After the checklist → if zero findings remain, output: {{"findings": []}}

===============================================================================

FINAL RULE: Pattern matching = noise. Proven taint path = finding. When in doubt, return {{"findings": []}}.
False negatives are recoverable. False positives destroy trust.

===============================================================================

RULE_ID MAPPING (MANDATORY):

You MUST map each finding to a specific rule_id. Use this exact format:

**For XSS/DOM Issues**:
- "RULE_11_STEP0: Static Dangerous Content" (hardcoded XSS, innerHTML with <script>)

**For Command Injection**:
- "RULE_102: Shell Injection" (subprocess with shell=True, os.system)

**For Code Injection**:
- "RULE_101: Eval Injection" (eval(), exec(), compile())

**For SQL Injection**:
- "RULE_103: SQL Injection" (string concatenation in SQL)

**For Hardcoded Secrets**:
- "RULE_100: Hardcoded Secrets" (API keys, passwords, tokens)

**For Data Leaks**:
- "RULE_105: Logging Gate" (sensitive data in logs)
- "RULE_104: PHI Protection" (PII/PHI in insecure sinks)

**For Custom Rules** (if system_rules.md has RULE_8, RULE_9, etc.):
- Use exact format: "RULE_8: PHI_PROTECTION"

**NEVER use "NONE" or leave empty**. If no specific rule matches, use:
- "RULE_11_STEP0: Static Dangerous Content" (for hardcoded dangerous strings)
- "RULE_11: Multi-Hop Taint Analysis" (for dynamic taint flows)

===============================================================================

OUTPUT FORMAT — respond with ONLY this JSON, no markdown, no extra text:

{{"findings": [
  {{
    "is_vulnerable": true,
    "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
    "rule_id": "<use exact format from RULE_ID MAPPING above>",
    "vulnerability_type": "Brief type",
    "line_number": <exact line number from prepended code, or null>,
    "description": "Proven taint: [UntrustedSource] reaches [DangerousSink] without sanitization."
  }}
]}}

FEW-SHOT EXAMPLES:

Example 1 (Hardcoded XSS):
{{"findings": [{{"severity": "CRITICAL", "rule_id": "RULE_11_STEP0: Static Dangerous Content", "vulnerability_type": "DOM-based XSS", "line_number": 4, "description": "Hardcoded XSS payload '<script>alert(1)</script>' passed to innerHTML"}}]}}

Example 2 (eval with hardcoded string):
{{"findings": [{{"severity": "CRITICAL", "rule_id": "RULE_101: Eval Injection", "vulnerability_type": "Code Injection", "line_number": 1, "description": "eval() called with hardcoded dangerous string"}}]}}

Example 3 (Safe code):
{{"findings": []}}

If safe: {{"findings": []}}"""

STRUCTURAL_INTEGRITY_SYSTEM_LLAMA = r"""
You are a code security auditor. Output ONLY valid JSON. No prose. No markdown. No explanation.

MANDATORY CHECKS (flag ONLY if exploitable):

1. COMMAND SAFETY (exploitability-based):
   - shell=True in subprocess with user-controlled arguments (CRITICAL)
   - os.system() with user input (CRITICAL)
   - eval(), exec(), compile() with user input (CRITICAL)
   - spawn() with user-controlled binary or shell-mode arguments (CRITICAL)
   - spawn() with hardcoded binary and array arguments (SAFE - no flag)

2. SECRETS & CREDENTIALS:
   - Hardcoded API keys, tokens, passwords, secrets (CRITICAL)
   - ONLY flag actual plaintext strings assigned directly in the code
   - DO NOT flag os.getenv(), process.env, or environment variable usage

3. DATA LEAKS:
   - console.log() with sensitive data (tokens, passwords, secrets)
   - Error responses that expose stack traces or internal paths

4. INJECTION FLAWS:
   - SQL concatenation (not parameterized queries)
   - Template injection (Jinja2, EJS, etc.)
   - Path traversal (path.join with user input)

ZERO-TOLERANCE NO-WEASEL MANDATE:
FORBIDDEN phrases: "Although hardcoded", "Despite being an array", "Could potentially"
These phrases = discard the finding immediately.

HARDCODED IS ALWAYS SAFE:
- subprocess.run(["cmd", "arg"]) → hardcoded array → NO FLAG
- os.environ["KEY"] = "1" → assigning literal → NO FLAG

OUTPUT FORMAT — respond with ONLY this JSON:

{{"findings": [
  {{
    "is_vulnerable": true,
    "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
    "vulnerability_type": "Brief type",
    "line_number": <exact line number from prepended code, or null>,
    "description": "Proven taint: [UntrustedSource] reaches [DangerousSink] without sanitization."
  }}
]}}

If safe: {{"findings": []}}
"""

METAGATE_AUDIT_SYSTEM = r"""
SYSTEM: You are the SEMANTICGUARD META-GATE. You are the final authority on vault changes.
You evaluate changes to the Architectural Pillars (.semanticguard/*.md files).

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
    Constructs the final prompt with BYOK rules integration and line numbers.
    Uses the perfected prompt structure from stress_test.py.
    """
    
    # Format dynamic rules block only if system_rules provided
    rules_block = f"""
===============================================================================

PROJECT-SPECIFIC SECURITY RULES (Loaded from system_rules.md):

{system_rules}

===============================================================================
""" if system_rules.strip() else ""
    
    # ALL models need explicit JSON reminder
    json_reminder = """

IMPORTANT: Output ONLY the JSON object specified above. No prose. No explanation. No markdown. Start with { and end with }
"""
    
    # Llama gets minimal prompt, DeepSeek gets full structured prompt
    if "llama" in (model_name or "").lower():
        return f"""{rules_block}

CODE TO AUDIT:
{user_command}

{json_reminder}"""
    
    # DeepSeek gets the full structured prompt
    return f"""{rules_block}

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
