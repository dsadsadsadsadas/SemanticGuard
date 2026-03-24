"""
SemantGuard V2.0 — Layer 1: Deterministic Pre-Screener

Catches obvious violations instantly using regex and AST pattern matching.
No model involved. Zero GPU usage.
"""
import re
import ast
import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger("semantguard.engine.layer1")

# ── VIOLATION RESULT ────────────────────────────────────────────────────────

@dataclass
class Layer1Violation:
    rule_id: str
    rule_name: str
    line_number: int
    matched_text: str
    severity: str  # CRITICAL / HIGH / MEDIUM
    description: str
    suggested_fix: str

@dataclass
class Layer1Result:
    violations: List[Layer1Violation] = field(default_factory=list)
    verdict: str = "ACCEPT"  # ACCEPT | REJECT
    screener_ran: bool = True
    details: str = ""
    
    def add_violation(self, v: Layer1Violation):
        self.violations.append(v)
        self.verdict = "REJECT"

# ── RULE DEFINITIONS ────────────────────────────────────────────────────────

# Exploitability-based rules: Focus on real attack paths, not patterns
# Each rule: (rule_id, rule_name, pattern, severity, description, fix)

REGEX_RULES = [
    # HARDCODED SECRETS (always critical)
    (
        "L1-001",
        "Hardcoded Secret",
        r'(?i)(api_key|apikey|secret_key|password|passwd|token|auth_token)\s*=\s*["\'][^"\']{8,}["\']',
        "CRITICAL",
        "Hardcoded secret or API key detected in source code.",
        "Move secrets to environment variables or a secrets manager."
    ),
    
    # EXECUTION CONTROL: eval/exec with user input (CRITICAL)
    (
        "L1-002",
        "Eval With User Input",
        r'eval\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)',
        "CRITICAL",
        "eval() called with user-controlled input — remote code execution risk.",
        "Never use eval() with user input. Use ast.literal_eval() or json.loads() for safe parsing."
    ),
    (
        "L1-002B",
        "Exec With User Input",
        r'exec\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)',
        "CRITICAL",
        "exec() called with user-controlled input — remote code execution risk.",
        "Never use exec() with user input. Use subprocess with array arguments instead."
    ),
    
    # EXECUTION CONTROL: subprocess with shell=True (CRITICAL only if user input)
    (
        "L1-003",
        "Subprocess Shell=True With User Input",
        r'(?:os\.system|subprocess\.(?:call|run|Popen))\s*\([^)]*(?:userInput|req\.|request\.|params\.|query\.|body\.)[^)]*shell\s*=\s*True',
        "CRITICAL",
        "subprocess called with shell=True and user-controlled arguments — command injection risk.",
        "Remove shell=True and pass command as a list of arguments. Never use shell=True with user input."
    ),
    
    # EXECUTION CONTROL: spawn/subprocess with user-controlled binary (CRITICAL)
    (
        "L1-003B",
        "User-Controlled Binary Execution",
        r'(?:spawn|subprocess\.(?:call|run|Popen))\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)',
        "CRITICAL",
        "Executed binary is user-controlled — arbitrary code execution risk.",
        "Never allow user input to control the executed binary. Use a whitelist of allowed commands."
    ),
    
    # ENVIRONMENT VARIABLE INJECTION (HIGH only if execution-influencing vars from user input)
    (
        "L1-004",
        "Environment Variable Injection",
        r'(?:LD_PRELOAD|BASH_ENV|ZDOTDIR|PYTHONPATH|NODE_OPTIONS)\s*:\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)',
        "HIGH",
        "Execution-influencing environment variable is user-controlled — privilege escalation risk.",
        "Never allow user input to control LD_PRELOAD, BASH_ENV, ZDOTDIR, PYTHONPATH, or NODE_OPTIONS."
    ),
    
    # SQL INJECTION (HIGH only if user input in query)
    (
        "L1-005",
        "SQL Injection",
        r'(?:execute|query)\s*\(\s*[f"\'].*(?:\+|%s|format|\{)[^)]*(?:userInput|req\.|request\.|params\.|query\.|body\.)',
        "HIGH",
        "SQL query constructed with string concatenation and user input — SQL injection risk.",
        "Use parameterized queries or an ORM. Never concatenate user input into SQL strings."
    ),
    
    # DATA LEAKS: Logging sensitive data
    (
        "L1-006",
        "Sensitive Data Logging",
        r'(?:console\.log|print|logger\.(?:info|debug|warn|error))\s*\([^)]*(?:password|token|secret|api_key|credential|auth)[^)]*\)',
        "HIGH",
        "Sensitive data (password, token, secret) logged to console or logger.",
        "Remove sensitive data from logs. Use a secure logger that redacts sensitive fields."
    ),
    
    # DATA LEAKS: Error stack traces exposed
    (
        "L1-007",
        "Error Stack Trace Exposed",
        r'(?:res\.json|res\.send|response\.json)\s*\([^)]*(?:err\.stack|error\.stack|e\.stack)',
        "HIGH",
        "Error stack trace exposed in API response — leaks internal architecture.",
        "Return a generic error message. Log the stack trace server-side only."
    ),
    
    # UNSAFE DESERIALIZATION (CRITICAL only if user input)
    (
        "L1-008",
        "Unsafe Deserialization",
        r'(?:pickle\.loads?|yaml\.load|json\.loads)\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)',
        "CRITICAL",
        "Unsafe deserialization of user-controlled data — arbitrary code execution risk.",
        "Use safe deserialization: pickle.loads() with restricted unpickler, yaml.safe_load(), json.loads()."
    ),
]

# ── AST-BASED RULES (Python only) ──────────────────────────────────────────

def _is_user_controlled(node: ast.expr, source_lines: List[str]) -> bool:
    """
    Heuristic: Check if an AST node represents user-controlled input.
    Returns True if node looks like: req.*, request.*, params.*, query.*, body.*, userInput, etc.
    """
    if isinstance(node, ast.Name):
        name = node.id.lower()
        return any(x in name for x in ['user', 'input', 'param', 'query', 'body', 'req', 'request', 'arg'])
    
    if isinstance(node, ast.Attribute):
        # Check for req.*, request.*, params.*, etc.
        if isinstance(node.value, ast.Name):
            base = node.value.id.lower()
            return any(x in base for x in ['req', 'request', 'param', 'query', 'body', 'user', 'input', 'arg'])
    
    if isinstance(node, ast.Subscript):
        # Check for dict[key] patterns
        if isinstance(node.value, ast.Name):
            base = node.value.id.lower()
            return any(x in base for x in ['req', 'request', 'param', 'query', 'body', 'user', 'input', 'arg'])
    
    return False

def _get_call_name(node: ast.Call) -> str:
    """Extract function name from a Call node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Name):
            return f"{node.func.value.id}.{node.func.attr}"
    return ""

def _check_ast_rules(source_code: str) -> List[Layer1Violation]:
    """
    Run AST-based checks on Python source code.
    Exploitability-based: Only flag if real attack path exists.
    """
    violations = []
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return violations  # Not Python — skip silently
    
    source_lines = source_code.split("\n")
    
    for node in ast.walk(tree):
        # ── EXECUTION CONTROL: eval/exec with user input ──
        if isinstance(node, ast.Call):
            call_name = _get_call_name(node)
            
            # eval() with user input
            if call_name == "eval" and node.args:
                if _is_user_controlled(node.args[0], source_lines):
                    violations.append(Layer1Violation(
                        rule_id="L1-002",
                        rule_name="Eval With User Input",
                        line_number=node.lineno,
                        matched_text=f"eval() call at line {node.lineno}",
                        severity="CRITICAL",
                        description="eval() called with user-controlled input — remote code execution risk.",
                        suggested_fix="Never use eval() with user input. Use ast.literal_eval() or json.loads() for safe parsing."
                    ))
            
            # exec() with user input
            if call_name == "exec" and node.args:
                if _is_user_controlled(node.args[0], source_lines):
                    violations.append(Layer1Violation(
                        rule_id="L1-002B",
                        rule_name="Exec With User Input",
                        line_number=node.lineno,
                        matched_text=f"exec() call at line {node.lineno}",
                        severity="CRITICAL",
                        description="exec() called with user-controlled input — remote code execution risk.",
                        suggested_fix="Never use exec() with user input. Use subprocess with array arguments instead."
                    ))
            
            # subprocess.Popen/call/run with shell=True and user input
            if call_name in ["subprocess.Popen", "subprocess.call", "subprocess.run", "os.system"]:
                has_shell_true = False
                has_user_input = False
                
                # Check for shell=True keyword argument
                for keyword in node.keywords:
                    if keyword.arg == "shell":
                        if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                            has_shell_true = True
                
                # Check if any positional argument is user-controlled
                for arg in node.args:
                    if _is_user_controlled(arg, source_lines):
                        has_user_input = True
                
                if has_shell_true and has_user_input:
                    violations.append(Layer1Violation(
                        rule_id="L1-003",
                        rule_name="Subprocess Shell=True With User Input",
                        line_number=node.lineno,
                        matched_text=f"{call_name}() call at line {node.lineno}",
                        severity="CRITICAL",
                        description="subprocess called with shell=True and user-controlled arguments — command injection risk.",
                        suggested_fix="Remove shell=True and pass command as a list of arguments. Never use shell=True with user input."
                    ))
        
        # ── BARE EXCEPT CLAUSES (silent failures) ──
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            violations.append(Layer1Violation(
                rule_id="L1-010",
                rule_name="Bare Except Clause",
                line_number=node.lineno,
                matched_text=f"bare except: at line {node.lineno}",
                severity="MEDIUM",
                description="Bare except clause catches all exceptions including KeyboardInterrupt — silent failure risk.",
                suggested_fix="Catch specific exception types explicitly."
            ))
        
        # ── ASSERT STATEMENTS (stripped by optimizer) ──
        if isinstance(node, ast.Assert):
            violations.append(Layer1Violation(
                rule_id="L1-009",
                rule_name="Assert Used For Security Check",
                line_number=node.lineno,
                matched_text=f"assert statement at line {node.lineno}",
                severity="MEDIUM",
                description="assert statements are stripped by Python optimizer (-O flag). Never use for security checks.",
                suggested_fix="Replace with explicit if/raise validation."
            ))
    
    return violations

# ── MAIN SCREENER ────────────────────────────────────────────────────────────

def screen(source_code: str, file_extension: str = ".py") -> Layer1Result:
    """
    Run Layer 1 deterministic screening on source code.
    Returns Layer1Result with all violations found.
    Runs in O(N) time — no model calls, no GPU.
    """
    result = Layer1Result()
    lines = source_code.split("\n")
    
    # Run regex rules line by line
    for rule_id, rule_name, pattern, severity, description, fix in REGEX_RULES:
        compiled = re.compile(pattern, re.IGNORECASE)
        for line_num, line in enumerate(lines, 1):
            match = compiled.search(line)
            if match:
                result.add_violation(Layer1Violation(
                    rule_id=rule_id,
                    rule_name=rule_name,
                    line_number=line_num,
                    matched_text=line.strip()[:120],
                    severity=severity,
                    description=description,
                    suggested_fix=fix
                ))
    
    # Run AST rules for Python files
    if file_extension.lower() == ".py":
        ast_violations = _check_ast_rules(source_code)
        for v in ast_violations:
            result.add_violation(v)
    
    if result.violations:
        result.details = f"Layer 1 caught {len(result.violations)} violation(s) without model inference."
        logger.info(f"Layer 1 REJECT — {len(result.violations)} violation(s) found")
    else:
        result.details = "Layer 1 found no obvious violations. Passing to model pipeline."
        logger.debug("Layer 1 ACCEPT — no obvious violations")
    
    return result
