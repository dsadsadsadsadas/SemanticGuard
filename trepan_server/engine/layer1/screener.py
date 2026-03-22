"""
Trepan V2.0 — Layer 1: Deterministic Pre-Screener

Catches obvious violations instantly using regex and AST pattern matching.
No model involved. Zero GPU usage.
"""
import re
import ast
import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger("trepan.engine.layer1")

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

# Each rule: (rule_id, rule_name, pattern, severity, description, fix)
REGEX_RULES = [
    (
        "L1-001",
        "Hardcoded Secret",
        r'(?i)(api_key|apikey|secret_key|password|passwd|token|auth_token)\s*=\s*["\'][^"\']{8,}["\']',
        "CRITICAL",
        "Hardcoded secret or API key detected in source code.",
        "Move secrets to environment variables or a secrets manager."
    ),
    (
        "L1-002",
        "Eval With Input",
        r'eval\s*\([^)]*(?:input|request|req|user|param|query|body)[^)]*\)',
        "CRITICAL",
        "eval() called with user-controlled input — remote code execution risk.",
        "Never use eval() with user input. Validate and sanitize input explicitly."
    ),
    (
        "L1-003",
        "Shell Injection",
        r'(?:os\.system|subprocess\.call|subprocess\.run|subprocess\.Popen)\s*\([^)]*shell\s*=\s*True',
        "CRITICAL",
        "subprocess called with shell=True — command injection risk.",
        "Remove shell=True and pass command as a list of arguments."
    ),
    (
        "L1-004",
        "SQL String Concatenation",
        r'(?:execute|query)\s*\(\s*[f"\'].*(?:\+|%s|format|\{)[^)]*(?:input|request|req|user|param|id|name)',
        "HIGH",
        "SQL query constructed with string concatenation — SQL injection risk.",
        "Use parameterized queries or an ORM."
    ),
    (
        "L1-005",
        "Console Log With Request Data",
        r'console\.log\s*\([^)]*(?:req\.|request\.|body|params|query|password|token|secret)[^)]*\)',
        "HIGH",
        "console.log() called with request or sensitive data.",
        "Remove debug logs or use a secure logger that redacts sensitive fields."
    ),
    (
        "L1-006",
        "Print With Request Data",
        r'print\s*\([^)]*(?:req\.|request\.|body|params|query|password|token|secret)[^)]*\)',
        "HIGH",
        "print() called with request or sensitive data.",
        "Remove debug prints or use a secure logger."
    ),
    (
        "L1-007",
        "Error Stack Exposed",
        r'(?:res\.json|res\.send|response\.json)\s*\([^)]*(?:err\.stack|error\.stack|e\.stack)',
        "HIGH",
        "Error stack trace exposed in API response — leaks internal architecture.",
        "Return a generic error message. Log the stack trace server-side only."
    ),
    (
        "L1-008",
        "Pickle Unsafe Load",
        r'pickle\.loads?\s*\([^)]*(?:request|req|user|input|body|param)',
        "CRITICAL",
        "pickle.load() called with user input — arbitrary code execution risk.",
        "Never deserialize user-supplied data with pickle."
    ),
]

# ── AST-BASED RULES (Python only) ──────────────────────────────────────────

def _check_ast_rules(source_code: str) -> List[Layer1Violation]:
    """Run AST-based checks on Python source code."""
    violations = []
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return violations  # Not Python — skip silently
    
    for node in ast.walk(tree):
        # Check for assert statements in production code
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
        
        # Check for bare except clauses (silent failures)
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
