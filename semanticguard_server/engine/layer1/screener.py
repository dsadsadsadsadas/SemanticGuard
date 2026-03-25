"""
SemanticGuard V2.0 — Layer 1: Risk Surface Detection Screener

Sophisticated scoring system ported from stress_test.py.
Focuses on exploitability and risk surfaces, not just patterns.
Uses scoring threshold instead of binary pass/fail.
"""
import re
import ast
import logging
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("semanticguard.engine.layer1")

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
    risk_score: int = 0
    
    def add_violation(self, v: Layer1Violation):
        self.violations.append(v)
        self.verdict = "REJECT"

# ── RISK SURFACE DETECTION PATTERNS ────────────────────────────────────────

# Hard skip: test files and low-risk directories
HARD_SKIP_PATTERNS = {
    "test_file": r"\.test\.(ts|js)$",
    "spec_file": r"\.spec\.(ts|js)$",
    "test_dir": r"[/\\]test[s]?[/\\]",
    "mock_file": r"\.mock\.(ts|js)$",
}

# Hard skip: low-risk filename keywords
SAFE_FILENAME_KEYWORDS = {
    "css": r"(?i)(style|css|theme|color|icon|view|ui|component|button|input|label|modal|dialog|sidebar|toolbar|menu|widget)",
    "test": r"(?i)(test|spec|mock|fixture|stub)",
    "doc": r"(?i)(readme|doc|example|sample|demo)",
}

# Hard skip: low-risk content keywords
SAFE_CONTENT_KEYWORDS = {
    "css_content": r"(?i)(\.css|@media|@keyframes|background-color|border-radius|font-size|padding|margin)",
    "theme_content": r"(?i)(theme|color|palette|dark|light|accent|primary|secondary)",
    "ui_content": r"(?i)(react|vue|angular|component|jsx|tsx|\bdom\b)",
}

# EXPLOITABILITY KEYWORDS: +5 pts each (real attack paths)
EXPLOITABILITY_KEYWORDS = {
    "user_controlled_spawn": r"spawn\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)",
    "shell_true_subprocess": r"subprocess\s*\.\s*(?:call|run|Popen)\s*\([^)]*shell\s*=\s*True",
    "eval_with_input": r"eval\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)",
    "exec_with_input": r"exec\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)",
    "os_system_with_input": r"os\.system\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)",
    "env_injection": r"(?:LD_PRELOAD|BASH_ENV|ZDOTDIR|PYTHONPATH|NODE_OPTIONS)\s*:\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)",
}

# SYSTEM KEYWORDS: +2 pts each (Risk Surface Detection)
# Broad patterns to catch dangerous functions and risk surfaces
SYSTEM_KEYWORDS = {
    # Command execution (broad catch)
    "os_system": r"\bos\.system\s*\(",
    "subprocess_call": r"\bsubprocess\.",
    "spawn": r"\bspawn\s*\(",
    "popen": r"\bpopen\s*\(",
    "exec_call": r"\bexec\s*\(",
    
    # Code evaluation (broad catch)
    "eval_call": r"\beval\s*\(",
    "compile_call": r"\bcompile\s*\(",
    
    # File system access (Path Traversal detection)
    "file_open": r"\bopen\s*\(",
    "file_read": r"\.read\s*\(",
    "file_write": r"\.write\s*\(",
    "fs_module": r"\bfs\.",
    "path_join": r"\bpath\.join",
    "require_fs": r"require\s*\(\s*['\"]fs['\"]",
    "require_child": r"require\s*\(\s*['\"]child_process['\"]",
    
    # Network/HTTP
    "http": r"(?i)(http|https|request|response)",
    "fetch": r"\bfetch\s*\(",
    "axios": r"\baxios\.",
    
    # Database
    "database": r"(?i)(database|sql|query|connection|pool|sqlite3|cursor\.execute|SQLAlchemy|execute\()",
    "execute_query": r"(?i)(execute|query)\s*\(",
    
    # Authentication/Authorization/Session (Risk Surface)
    "auth": r"(?i)(authenticate|authorize|permission|role|access|login|session)",
    
    # Cryptography/RNG Risk (Risk Surface)
    "crypto": r"(?i)(crypto|encrypt|decrypt|hash|sign|verify|\brandom\.|Math\.random)",
    
    # Data Parsing Risk (Risk Surface)
    "data_parsing": r"(?i)(\bxml\.|ElementTree|yaml\.load)",
    "json_parse": r"JSON\.parse",
    "pickle_load": r"pickle\.load",
    
    # Insecure Deserialization/Validation (AUTOPSY FIX)
    "unvalidated_request_json": r"request\.json(?!.*(validate|sanitize|schema|jsonschema|pydantic|marshmallow))",
    "unvalidated_req_body": r"req\.body(?!.*(validate|sanitize|schema|joi|yup|zod))",
    
    # UI/Template Risk - XSS (Risk Surface)
    "ui_template": r"(?i)(render_template|html\.escape|\bjinja|innerHTML|template|format|<div|<h[1-6]|<html|html\s*=|f\"\"\"[\s\S]*?<|class=\")",
    
    # Secrets/Credentials (hardcoded detection)
    "hardcoded_key": r"(?i)(api_key|apikey|secret|password|token)\s*=\s*['\"][^'\"]{8,}['\"]",
    "aws_key": r"(?i)(aws_access_key|aws_secret)",
    "bearer_token": r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+",
    
    # Diagnostics additions from Autopsy Mode
    "concurrency": r"(?i)\b(threading|thread|mutex|lock)\b",
    "xml_advanced": r"(?i)(lxml|etree|XMLParser)",
    "cors_network": r"(?i)(\bcors\b|Access-Control-Allow)",
    "deep_link": r"(?i)(window\.location|\bhref\b)",
    "file_upload": r"(?i)(multer|formidable|req\.files?)",
    "graphql": r"(?i)(ApolloServer|\bgraphql\b|introspection)",
    "prototype_pollution": r"(?i)(__proto__|\.prototype\b|Object\.assign|\bmerge\b)",
    "redos_risk": r"(?i)(RegExp|\.match\(|\.test\()",
    "financial_logic": r"(?i)(transfer|balance|payment|transaction|checkout|invoice|amount)",
}

# UI PENALTIES: -3 pts each (low-risk UI code)
UI_PENALTIES = {
    "html_element": r"(?i)(HTMLElement|innerHTML|textContent|className)",
    "color": r"(?i)(color|Color|COLOR)",
    "theme": r"(?i)(theme|Theme|THEME)",
    "style": r"(?i)(style|Style|STYLE)",
    "view": r"(?i)(view|View|VIEW)",
}

# ── RISK SURFACE SCREENING LOGIC ───────────────────────────────────────────

def _is_hard_skip_file(file_path: str, code: str) -> Tuple[bool, str]:
    """Check if file should be hard-skipped (test, style, etc.)"""
    if not file_path:
        return False, ""
        
    filename = Path(file_path).name.lower()
    full_path = str(file_path).lower()
    
    # Check hard skip patterns
    for pattern_name, pattern in HARD_SKIP_PATTERNS.items():
        if re.search(pattern, full_path):
            return True, f"Hard skip: {pattern_name}"
    
    # Check safe filename keywords
    for keyword_type, pattern in SAFE_FILENAME_KEYWORDS.items():
        if re.search(pattern, filename):
            return True, f"Hard skip: {keyword_type} in filename"
    
    # Check safe content keywords (quick scan)
    for keyword_type, pattern in SAFE_CONTENT_KEYWORDS.items():
        if re.search(pattern, code[:2000]):  # Only scan first 2KB
            return True, f"Hard skip: {keyword_type} in content"
    
    return False, ""

def calculate_risk_score(code: str) -> int:
    """
    Calculate exploitability-based risk score.
    
    Scoring:
    - Exploitability Keywords: +5 pts each (real attack paths)
    - System Keywords: +2 pts each (needs context analysis)
    - UI Penalties: -3 pts each (low-risk UI code)
    
    Returns: risk score (0 or higher)
    """
    score = 0
    
    # Count exploitability keywords (real attack paths)
    for keyword_name, pattern in EXPLOITABILITY_KEYWORDS.items():
        matches = len(re.findall(pattern, code))
        score += matches * 5
    
    # Count system keywords (needs context)
    for keyword_name, pattern in SYSTEM_KEYWORDS.items():
        matches = len(re.findall(pattern, code))
        score += matches * 2
    
    # Apply UI penalties
    for keyword_name, pattern in UI_PENALTIES.items():
        matches = len(re.findall(pattern, code))
        score -= matches * 3
    
    # Ensure score doesn't go below 0
    return max(0, score)

def should_audit(code: str, file_extension: str, file_path: str = None) -> Tuple[bool, str, int]:
    """
    Exploitability-based filtering: only audit files with real attack paths.
    Returns (should_audit, reason, risk_score)
    
    HARD SKIP if:
    - File is .test.ts, .spec.ts, or in test/ folder
    - Filename contains: css, theme, icon, color, view, ui, component, etc.
    - Content is mostly CSS/theme/UI code
    
    AUDIT ONLY if:
    - File has exploitable execution control issues
    - File has system/network access that could be exploited
    """
    # Skip very small files (but allow test cases)
    if len(code) < 20:
        return False, "File too small (< 20 chars)", 0
    
    if file_extension.lower() in ['.md', '.markdown', '.txt', '.json', '.yaml', '.yml', '.lock', '.env', '.toml', '.ini', '.cfg', '.css', '.scss', '.less']:
        return False, "Non-executable file type", 0
    
    # Hard skip test/style/ui files
    if file_path:
        is_skip, reason = _is_hard_skip_file(file_path, code)
        if is_skip:
            return False, reason, 0
    
    # Calculate risk score (exploitability-based)
    risk_score = calculate_risk_score(code)
    
    # POSITIVE FILTER: must have at least ONE exploitable keyword (score > 0)
    if risk_score > 0:
        return True, f"Exploitability score: {risk_score}", risk_score
    
    # Default: skip (no exploitable patterns found)
    return False, "No exploitable attack paths detected", 0

# ── MAIN SCREENER ────────────────────────────────────────────────────────────

def screen(source_code: str, file_extension: str = ".py", file_path: str = None) -> Layer1Result:
    """
    Run Layer 1 risk surface detection screening on source code.
    Uses sophisticated scoring system from stress_test.py.
    Returns Layer1Result with verdict based on risk score threshold.
    """
    result = Layer1Result()
    
    # Apply risk surface detection logic
    should_audit_file, reason, risk_score = should_audit(source_code, file_extension, file_path)
    result.risk_score = risk_score
    
    if not should_audit_file:
        result.verdict = "ACCEPT"
        result.details = f"Layer 1 ACCEPT: {reason}"
        logger.debug(f"Layer 1 ACCEPT — {reason}")
        return result
    
    # File passed risk surface detection - now check for critical violations
    lines = source_code.split("\n")
    
    # Check for exploitability keywords (immediate REJECT)
    for keyword_name, pattern in EXPLOITABILITY_KEYWORDS.items():
        compiled = re.compile(pattern, re.IGNORECASE)
        for line_num, line in enumerate(lines, 1):
            match = compiled.search(line)
            if match:
                result.add_violation(Layer1Violation(
                    rule_id="L1-EXPLOIT",
                    rule_name=f"Exploitability: {keyword_name}",
                    line_number=line_num,
                    matched_text=line.strip()[:120],
                    severity="CRITICAL",
                    description=f"Exploitable pattern detected: {keyword_name}",
                    suggested_fix="Review for user input validation and sanitization."
                ))
    
    # Check for hardcoded secrets (immediate REJECT)
    hardcoded_pattern = r'(?i)(api_key|apikey|secret_key|password|passwd|token|auth_token)\s*=\s*["\'][^"\']{8,}["\']'
    compiled = re.compile(hardcoded_pattern, re.IGNORECASE)
    for line_num, line in enumerate(lines, 1):
        match = compiled.search(line)
        if match:
            result.add_violation(Layer1Violation(
                rule_id="L1-SECRET",
                rule_name="Hardcoded Secret",
                line_number=line_num,
                matched_text=line.strip()[:120],
                severity="CRITICAL",
                description="Hardcoded secret or API key detected in source code.",
                suggested_fix="Move secrets to environment variables or a secrets manager."
            ))
    
    if result.violations:
        result.details = f"Layer 1 REJECT: {len(result.violations)} critical violation(s) found (Risk Score: {risk_score})"
        logger.info(f"Layer 1 REJECT — {len(result.violations)} violation(s) found, risk score: {risk_score}")
    else:
        result.verdict = "ACCEPT"
        result.details = f"Layer 1 ACCEPT: Risk surface detected but no critical violations (Risk Score: {risk_score})"
        logger.info(f"Layer 1 ACCEPT — risk surface detected, passing to Layer 2 (risk score: {risk_score})")
    
    return result