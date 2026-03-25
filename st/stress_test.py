#!/usr/bin/env python3
"""
[SHIELD] Trepan Enterprise Stress Test
Zero-shot security audit of massive codebases via Groq API
Dynamic rate limiting with Token Bucket algorithm
"""

import os
import sys
import time
import json
import asyncio
import requests
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from collections import deque
import getpass

# Import Layer 1 screener for pre-filtering
try:
    from trepan_server.engine.layer1.screener import screen as layer1_screen
    LAYER1_AVAILABLE = True
except ImportError:
    LAYER1_AVAILABLE = False

# Import sanity tests
try:
    from sanity_tests import run_internal_sanity_tests
    SANITY_TESTS_AVAILABLE = True
except ImportError:
    SANITY_TESTS_AVAILABLE = False

# Import the new TokenBucket implementation
from token_bucket import TokenBucket

# --- ANSI Color Codes --------------------------------------------------------

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    DIM = '\033[2m'

def colored(text: str, color: str) -> str:
    return f"{color}{text}{Colors.ENDC}"

# --- Configuration ----------------------------------------------------------

@dataclass
class Config:
    api_key: str
    model: str
    max_rpm: int
    max_tpm: int
    codebase_path: str
    file_extensions: List[str]
    max_file_size_kb: int = 500
    timeout_seconds: int = 60

GROQ_MODELS = {
    "1": {
        "name": "llama-3.3-70b-versatile",
        "display": "Llama 3.3 70B Versatile",
        "max_rpm": 30,
        "max_tpm": 12000
    },
    "2": {
        "name": "meta-llama/llama-4-scout-17b-16e-instruct",
        "display": "Llama 4 Scout 17B",
        "max_rpm": 30,
        "max_tpm": 30000
    },
    "3": {
        "name": "custom",
        "display": "Custom Model (Manual TPM Entry)",
        "max_rpm": None,  # Will be prompted
        "max_tpm": None   # Will be prompted
    }
}

# --- Layer 1 Pre-Screener (AST/Regex) --------------------------------------

class Layer1PreScreener:
    """
    Exploitability-Based Security Filtering.
    Analyzes execution control surfaces and environment variable injection.
    Reduces false positives by focusing on real attack paths.
    """
    
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
    
    @staticmethod
    def _is_hard_skip_file(file_path: Path, code: str) -> Tuple[bool, str]:
        """Check if file should be hard-skipped (test, style, etc.)"""
        filename = file_path.name.lower()
        full_path = str(file_path).lower()
        
        # Check hard skip patterns
        for pattern_name, pattern in Layer1PreScreener.HARD_SKIP_PATTERNS.items():
            if re.search(pattern, full_path):
                return True, f"Hard skip: {pattern_name}"
        
        # Check safe filename keywords
        for keyword_type, pattern in Layer1PreScreener.SAFE_FILENAME_KEYWORDS.items():
            if re.search(pattern, filename):
                return True, f"Hard skip: {keyword_type} in filename"
        
        # Check safe content keywords (quick scan)
        for keyword_type, pattern in Layer1PreScreener.SAFE_CONTENT_KEYWORDS.items():
            if re.search(pattern, code[:2000]):  # Only scan first 2KB
                return True, f"Hard skip: {keyword_type} in content"
        
        return False, ""
    
    @staticmethod
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
        for keyword_name, pattern in Layer1PreScreener.EXPLOITABILITY_KEYWORDS.items():
            matches = len(re.findall(pattern, code))
            score += matches * 5
        
        # Count system keywords (needs context)
        for keyword_name, pattern in Layer1PreScreener.SYSTEM_KEYWORDS.items():
            matches = len(re.findall(pattern, code))
            score += matches * 2
        
        # Apply UI penalties
        for keyword_name, pattern in Layer1PreScreener.UI_PENALTIES.items():
            matches = len(re.findall(pattern, code))
            score -= matches * 3
        
        # Ensure score doesn't go below 0
        return max(0, score)
    
    @staticmethod
    def should_audit(code: str, file_extension: str, file_path: Path = None) -> Tuple[bool, str, int]:
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
        # Skip non-code files
        if len(code) < 100:
            return False, "File too small (< 100 chars)", 0
        
        if file_extension.lower() in ['.md', '.markdown', '.txt', '.json', '.yaml', '.yml', '.lock', '.env', '.toml', '.ini', '.cfg', '.css', '.scss', '.less']:
            return False, "Non-executable file type", 0
        
        # Hard skip test/style/ui files
        if file_path:
            is_skip, reason = Layer1PreScreener._is_hard_skip_file(file_path, code)
            if is_skip:
                return False, reason, 0
        
        # Calculate risk score (exploitability-based)
        risk_score = Layer1PreScreener.calculate_risk_score(code)
        
        # POSITIVE FILTER: must have at least ONE exploitable keyword (score > 0)
        if risk_score > 0:
            return True, f"Exploitability score: {risk_score}", risk_score
        
        # Default: skip (no exploitable patterns found)
        return False, "No exploitable attack paths detected", 0

# --- File Scanner ----------------------------------------------------------

class CodebaseScanner:
    def __init__(self, codebase_path: str, extensions: List[str], max_size_kb: int):
        self.codebase_path = Path(codebase_path)
        self.extensions = extensions
        self.max_size_kb = max_size_kb
        self.files = []
        self.file_scores = {}  # Map file path to risk score
        self.skipped_files = []
        
    def scan(self) -> List[Path]:
        """Recursively scan codebase for auditable files, applying Layer1PreScreener and risk scoring"""
        print(f"\n{colored('[SCAN] Scanning codebase...', Colors.CYAN)}")
        
        # -- SINGLE FILE MODE ------------------------------------------------
        if self.codebase_path.is_file():
            file_path = self.codebase_path
            size_kb = file_path.stat().st_size / 1024
            if size_kb > self.max_size_kb:
                self.skipped_files.append((file_path, f"File too large ({size_kb:.1f}KB)"))
            else:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        code = f.read()
                    # For single files: always bypass Layer 1 hard-skips and run the LLM.
                    # User explicitly chose this file, so we trust their intent.
                    risk_score = Layer1PreScreener.calculate_risk_score(code)
                    self.files.append(file_path)
                    self.file_scores[str(file_path)] = risk_score
                    print(f"{colored(f'? Single file mode ? queuing {file_path.name} (risk score: {risk_score})', Colors.GREEN)}")
                except Exception as e:
                    self.skipped_files.append((file_path, f"Read error: {str(e)}"))
            print(f"{colored(f'[SKIP] Filtered {len(self.skipped_files)} files (safe/boilerplate)', Colors.DIM)}")
            return self.files
        # --------------------------------------------------------------------

        skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build', '.next', 'out', 'coverage'}
        
        for ext in self.extensions:
            pattern = f"**/*{ext}"
            for file_path in self.codebase_path.glob(pattern):
                # Skip excluded directories
                if any(skip_dir in file_path.parts for skip_dir in skip_dirs):
                    continue
                
                # Check file size
                size_kb = file_path.stat().st_size / 1024
                if size_kb > self.max_size_kb:
                    self.skipped_files.append((file_path, f"File too large ({size_kb:.1f}KB)"))
                    continue
                
                # Apply Layer1PreScreener
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        code = f.read()
                    
                    should_audit, reason, risk_score = Layer1PreScreener.should_audit(code, file_path.suffix, file_path)
                    if should_audit:
                        self.files.append(file_path)
                        self.file_scores[str(file_path)] = risk_score
                    else:
                        self.skipped_files.append((file_path, reason))
                except Exception as e:
                    self.skipped_files.append((file_path, f"Read error: {str(e)}"))
        
        # Sort files by risk score (highest first)
        self.files.sort(key=lambda f: self.file_scores.get(str(f), 0), reverse=True)
        
        print(f"{colored(f'? Found {len(self.files)} high-risk files', Colors.GREEN)}")
        print(f"{colored(f'[SKIP] Filtered {len(self.skipped_files)} files (safe/boilerplate)', Colors.DIM)}")
        return self.files

# --- Groq API Client --------------------------------------------------------

class GroqAuditClient:
    def __init__(self, api_key: str, model: str, rate_limiter: TokenBucket):
        self.api_key = api_key
        self.model = model
        self.rate_limiter = rate_limiter
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"
        self.vulnerabilities_found = []
        self.files_scanned = 0
        self.total_tokens = 0
        
    def get_system_prompt(self) -> str:
        # Phase 1: Dynamic Rule Ingestion from .semanticguard/system_rules.md
        rules_dir = Path(__file__).parent.parent
        rules_path = rules_dir / ".semanticguard" / "system_rules.md"
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                dynamic_rules = f.read().strip()
        except FileNotFoundError:
            dynamic_rules = ""
        
        # Format dynamic rules block only if file was found
        rules_block = f"""
===============================================================================

PROJECT-SPECIFIC SECURITY RULES (Loaded from security_rules.md):

{dynamic_rules}

===============================================================================
""" if dynamic_rules else ""
        
        return f"""You are an AGGRESSIVE AppSec auditor focused on EXPLOITABILITY, not patterns.

Your job is to find REAL, EXPLOITABLE security issues. Avoid false positives.

===============================================================================
{rules_block}
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

PHASE 1 ? LINE NUMBER RULE (MANDATORY):

The code you receive has LINE NUMBERS prepended in the format "123: code here".
You MUST use ONLY these exact line numbers. NEVER invent or extrapolate one.
If you cannot pinpoint the exact line, set "line_number" to null.

===============================================================================

PHASE 2 ? STRICT SOURCE-TO-SINK TAINT ANALYSIS (MANDATORY):

Before flagging ANYTHING, trace it: Source ? every variable ? Sink.
Only flag if UNTRUSTED user input (request body, query param, file upload, CLI arg) reaches a dangerous sink WITHOUT sanitization.

Trusted sources (do NOT flag):  hardcoded literals, script constants, os.getenv(), os.environ.copy()
Untrusted sources (trace these): request.json(), req.query, sys.argv[1+], form data, user session values

HARDCODED IS ALWAYS SAFE:
- subprocess.run(["cmd", "arg"]) ? hardcoded array ? NO FLAG
- subprocess.Popen(["ollama", "serve"], env=os.environ.copy()) ? NO FLAG
- os.environ["KEY"] = "1" ? assigning literal ? NO FLAG
- requests.get(CONSTANT_URL) where CONSTANT_URL is defined in-file ? NO FLAG

===============================================================================

PHASE 3 ? ZERO-TOLERANCE NO-WEASEL MANDATE:

You are FORBIDDEN from creating a finding if your own reasoning uses ANY of these:
  "Although hardcoded" / "Despite being an array" / "Although the arguments are hardcoded"
  "Although the binary is hardcoded" / "Could potentially" / "An attacker could potentially"

These phrases prove you already know the code is SAFE. These phrases = discard the finding.
A finding that admits inputs are hardcoded is a LOGIC FAILURE.

===============================================================================

PHASE 4 ? SECRET vs CONFIG:

ONLY flag as "Hardcoded Secret" if the value is an auth credential:
  Real secrets:  API_KEY = "sk-live-abc123"  |  password = "Secret!"  |  token = "gsk_xyz"
  NOT secrets:   MODEL_NAME = "llama3.1:8b"  |  PORT = "8001"  |  HOST = "0.0.0.0"  |  URL = "http://localhost:11434"

Ask: "Would this appear in a public README?" If yes ? NOT a secret. No flag.

===============================================================================

PHASE 5 ? PRE-FLIGHT CHECKLIST (mandatory before writing any JSON):

For EVERY potential finding:
  Q1: Can an attacker change this value without already having shell access? NO ? REMOVE IT.
  Q2: Does my reasoning use a weasel phrase from Phase 3?               YES ? REMOVE IT.
  Q3: Is the "secret" a model name, port, host, or local URL?           YES ? REMOVE IT.

After the checklist ? if zero findings remain, output: {{"findings": []}}

===============================================================================

FINAL RULE: Pattern matching = noise. Proven taint path = finding. When in doubt, return {{"findings": []}}.
False negatives are recoverable. False positives destroy trust.

OUTPUT FORMAT ? respond with ONLY this JSON, no markdown, no extra text:

{{"findings": [
  {{
    "is_vulnerable": true,
    "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
    "vulnerability_type": "Brief type",
    "line_number": <exact line number from prepended code, or null>,
    "description": "Proven taint: [UntrustedSource] reaches [DangerousSink] without sanitization."
  }}
]}}

If safe: {{"findings": []}}"""
    
    async def audit_file(self, file_path: Path, current: int = None, total: int = None, file_token_count: int = None) -> Dict:
        """Audit a single file with global leaky bucket rate limiting
        
        Uses globally shared token state with asyncio.Lock() to prevent bursts.
        Skips files > 25,000 tokens (too large for free tier).
        
        Args:
            file_path: Path to the file to audit
            current: Current file index (for progress display)
            total: Total files to audit (for progress display)
            file_token_count: Pre-calculated token count for this file
        """
        max_retries = 3
        retry_count = 0
        
        def get_timestamp():
            """Get current timestamp with milliseconds"""
            now = datetime.now()
            return now.strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
        
        # Read file
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()
        
        # Prepend line numbers to every line so the LLM can reference them precisely
        numbered_lines = [f"{i+1}: {line}" for i, line in enumerate(code.splitlines())]
        numbered_code = "\n".join(numbered_lines)
        
        # Estimate tokens (rough: 1 token ? 4 chars)
        estimated_tokens = len(numbered_code) // 4 + 500
        
        # Check if file is too large for free tier
        if estimated_tokens > self.rate_limiter.max_file_tokens:
            timestamp = get_timestamp()
            print(f"{colored(f'[{timestamp}] [SKIP: {estimated_tokens:,} tokens > {self.rate_limiter.max_file_tokens:,} max]', Colors.YELLOW)}")
            return {
                "file": str(file_path),
                "status": "skipped",
                "reason": f"File too large ({estimated_tokens:,} tokens)",
                "latency": 0
            }
        
        # Task 2: Account for LLM output tokens (reserve 2000 tokens for response)
        # Consume input tokens + 2000 for the AI's response
        total_tokens_to_consume = estimated_tokens + 2000
        
        # GLOBAL LEAKY BUCKET: Wait for token availability
        wait_time = await self.rate_limiter.consume_with_wait(total_tokens_to_consume)
        
        # Task 1: Print progress AFTER rate limiting completes
        # This ensures logging only happens when the file is actually being sent
        if current is not None and total is not None:
            timestamp = get_timestamp()
            print(f"{colored(f'[{timestamp}] [{current}/{total}]', Colors.CYAN)} {colored(file_path.name, Colors.DIM)} {colored(f'[{estimated_tokens:,} input + 2000 output tokens]', Colors.YELLOW)}")
        
        # Print throttling info with timestamp
        if wait_time > 0:
            timestamp = get_timestamp()
            print(f"{colored(f'[{timestamp}] [Wait: {wait_time:.2f}s for {total_tokens_to_consume:,} tokens]', Colors.CYAN)}")
        
        while retry_count <= max_retries:
            try:
                # Make API call (non-blocking via asyncio.to_thread)
                start_time = time.time()
                
                # 🔍 DEBUG INSTRUMENTATION: Capture raw payload before API call
                system_prompt = self.get_system_prompt()
                user_prompt = f"Audit this code (each line prefixed with its line number):\n\n{numbered_code}"
                DEBUG_PAYLOAD = {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "model": self.model,
                    "temperature": 0.3,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"}
                }
                with open("debug_stress_payload.json", "w", encoding="utf-8") as f:
                    json.dump(DEBUG_PAYLOAD, f, indent=2)
                print(f"{colored('[DEBUG] Payload written to debug_stress_payload.json', Colors.YELLOW)}")
                
                response = await asyncio.to_thread(
                    requests.post,
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 500,
                        "response_format": {"type": "json_object"}
                    },
                    timeout=60
                )
                
                elapsed = time.time() - start_time
                
                if response.status_code != 200:
                    # Refund tokens on error (we reserved total_tokens_to_consume)
                    self.rate_limiter.refund(total_tokens_to_consume, 0)
                    
                    # Self-healing: Special handling for 429 (rate limit) errors
                    if response.status_code == 429:
                        if retry_count < max_retries:
                            retry_count += 1
                            # Set global pause for ALL tasks
                            await self.rate_limiter.set_global_pause(30.0)
                            timestamp = get_timestamp()
                            print(f"{colored(f'[{timestamp}] [429 GLOBAL PAUSE! All tasks sleeping 30s...]', Colors.RED)}")
                            await asyncio.sleep(30)  # Wait 30 seconds for Groq to reset
                            continue
                        else:
                            return {
                                "file": str(file_path),
                                "status": "error",
                                "error": f"HTTP 429: Rate limit exceeded after {max_retries} retries",
                                "latency": elapsed
                            }
                    
                    # Retry on other timeout errors (408, 504)
                    if response.status_code in [408, 504] and retry_count < max_retries:
                        retry_count += 1
                        backoff_time = 15
                        timestamp = get_timestamp()
                        print(f"{colored(f'[{timestamp}] [HTTP {response.status_code} Error! Waiting {backoff_time:.2f}s before retry {retry_count}/{max_retries}...]', Colors.YELLOW)}")
                        await asyncio.sleep(backoff_time)
                        continue
                    
                    timestamp = get_timestamp()
                    print(f"{colored(f'[{timestamp}] [HTTP {response.status_code} Error: {response.text[:50]}]', Colors.RED)}")
                    return {
                        "file": str(file_path),
                        "status": "error",
                        "error": f"HTTP {response.status_code}: {response.text[:100]}",
                        "latency": elapsed
                    }
                
                data = response.json()
                tokens_used = data.get("usage", {}).get("total_tokens", estimated_tokens)
                result = data["choices"][0]["message"]["content"]
                
                # Refund difference if actual is lower than estimate
                # We reserved (estimated_tokens + 2000), so refund the difference
                self.rate_limiter.refund(total_tokens_to_consume, tokens_used)
                self.total_tokens += tokens_used
                self.files_scanned += 1
                
                # Phase 3: Parse findings array response
                any_vulnerable = False
                
                try:
                    parsed = json.loads(result.strip())
                    
                    # Normalize findings to a list
                    findings = []
                    if isinstance(parsed, list):
                        findings = parsed
                    elif isinstance(parsed, dict):
                        findings = parsed.get("findings", [])
                        # Handle stringified array
                        if isinstance(findings, str) and findings.strip().startswith("["):
                            try:
                                findings = json.loads(findings)
                            except:
                                findings = []
                        # Fallback to single-object schema
                        if (not findings or not isinstance(findings, list)) and "is_vulnerable" in parsed:
                            findings = [parsed]
                    
                    if not isinstance(findings, list):
                        findings = []

                    for finding in findings:
                        if not isinstance(finding, dict):
                            continue
                        if finding.get("is_vulnerable") is True:
                            any_vulnerable = True
                            severity = str(finding.get("severity", "UNKNOWN")).upper()
                            vuln_type = str(finding.get("vulnerability_type", "Unknown Voucherability"))
                            line = finding.get("line_number", "Unknown")
                            desc = str(finding.get("description", "No description provided."))
                            
                            violation_summary = f"[WARN]  [{severity}] {vuln_type} at line {line}: {desc}"
                            self.vulnerabilities_found.append({
                                "file": str(file_path),
                                "finding": violation_summary,
                                "summary": violation_summary,
                                "severity": severity,
                                "type": vuln_type,
                                "line": line
                            })
                
                except json.JSONDecodeError as e:
                    timestamp = get_timestamp()
                    print(f"{colored(f'[{timestamp}] [JSON Parse Error: {str(e)[:50]}]', Colors.RED)}")
                    return {
                        "file": str(file_path),
                        "status": "error",
                        "error": f"JSON parse error: {str(e)[:100]}",
                        "latency": elapsed,
                        "raw_response": result[:200]
                    }
                
                return {
                    "file": str(file_path),
                    "status": "vulnerable" if any_vulnerable else "safe",
                    "finding": self.vulnerabilities_found[-1]["summary"] if any_vulnerable else None,
                    "tokens": tokens_used,
                    "latency": elapsed
                }
            
            except (requests.Timeout, asyncio.TimeoutError) as e:
                if retry_count < max_retries:
                    retry_count += 1
                    backoff_time = 15
                    timestamp = get_timestamp()
                    print(f"{colored(f'[{timestamp}] [Timeout! Waiting {backoff_time:.2f}s before retry {retry_count}/{max_retries}...]', Colors.YELLOW)}")
                    await asyncio.sleep(backoff_time)
                    continue
                
                timestamp = get_timestamp()
                print(f"{colored(f'[{timestamp}] [Timeout Error after {max_retries} retries]', Colors.RED)}")
                return {
                    "file": str(file_path),
                    "status": "error",
                    "error": f"Timeout after {max_retries} retries",
                    "latency": 0
                }
            
            except Exception as e:
                timestamp = get_timestamp()
                print(f"{colored(f'[{timestamp}] [Exception: {str(e)[:50]}]', Colors.RED)}")
                return {
                    "file": str(file_path),
                    "status": "error",
                    "error": str(e),
                    "latency": 0
                }
        
        timestamp = get_timestamp()
        print(f"{colored(f'[{timestamp}] [Unknown error after retries]', Colors.RED)}")
        return {
            "file": str(file_path),
            "status": "error",
            "error": "Unknown error after retries",
            "latency": 0
        }
    
    async def audit_codebase(self, files: List[Path], concurrency: int = 1):
        """Audit multiple files with concurrency control, live timestamps, and token tracking"""
        print(f"\n{colored('>>> Starting audit...', Colors.CYAN)}")
        print(f"{colored(f'Model: {self.model} | Max RPM: {self.rate_limiter.max_rpm} | Max TPM: {self.rate_limiter.max_tpm:,}', Colors.DIM)}")
        print(f"{colored(f'Max File Size: {self.rate_limiter.max_file_tokens:,} tokens (20% of TPM capacity)', Colors.DIM)}\n")
        
        def get_timestamp():
            """Get current timestamp with milliseconds"""
            now = datetime.now()
            return now.strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
        
        def estimate_tokens(file_path: Path) -> int:
            """Estimate tokens for a file (1 token ? 4 chars)"""
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    code = f.read()
                return len(code) // 4 + 500
            except:
                return 500
        
        # Pre-calculate token counts for all files
        file_tokens = {}
        total_tokens_estimate = 0
        for file_path in files:
            tokens = estimate_tokens(file_path)
            file_tokens[str(file_path)] = tokens
            total_tokens_estimate += tokens
        
        semaphore = asyncio.Semaphore(concurrency)
        total_files = len(files)
        file_counter = {"count": 0}  # Shared counter for progress
        tokens_processed = {"count": 0}  # Shared token counter
        
        async def audit_with_semaphore(file_path):
            async with semaphore:
                file_counter["count"] += 1
                current = file_counter["count"]
                timestamp = get_timestamp()
                
                # Get token count for this file
                file_token_count = file_tokens.get(str(file_path), 500)
                
                # Enforce dynamic file cap based on TPM
                if file_token_count > self.rate_limiter.max_file_tokens:
                    print(f"{colored(f'[{timestamp}] [{current}/{total_files}] [SKIPPED]', Colors.YELLOW)} {colored(file_path.name, Colors.DIM)} {colored(f'is too large ({file_token_count:,} tokens > {self.rate_limiter.max_file_tokens:,} limit)', Colors.RED)}")
                    return {
                        "file": str(file_path),
                        "status": "skipped",
                        "reason": f"File too large ({file_token_count:,} tokens > {self.rate_limiter.max_file_tokens:,} limit)",
                        "latency": 0
                    }
                
                # Task 1: Print progress AFTER rate limiting completes (moved inside audit_file)
                # The logging will now happen after consume_with_wait() succeeds
                result = await self.audit_file(file_path, current, total_files, file_token_count)
                
                # Update tokens processed
                tokens_processed["count"] += file_token_count
                
                return result
        
        tasks = [audit_with_semaphore(f) for f in files]
        results = await asyncio.gather(*tasks)
        
        return results

# --- Terminal UI ------------------------------------------------------------

def print_header():
    print(f"\n{colored('==============================================================', Colors.BOLD)}")
    print(f"{colored('|', Colors.BOLD)}  {colored('[TREPAN ENTERPRISE STRESS TEST]', Colors.BOLD)}  {colored('|', Colors.BOLD)}")
    print(f"{colored('|', Colors.BOLD)}  {colored('Zero-Shot Security Audit via Groq', Colors.DIM)}  {colored('|', Colors.BOLD)}")
    print(f"{colored('==============================================================', Colors.BOLD)}\n")

def get_api_key() -> str:
    """Prompt for API key securely"""
    print(f"{colored('[KEY] Enter your Groq API Key (hidden):', Colors.CYAN)}")
    api_key = getpass.getpass("? ")
    if not api_key:
        print(f"{colored('[ERROR] API key cannot be empty', Colors.RED)}")
        sys.exit(1)
    return api_key

def detect_model_limits(api_key: str, model_name: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Detect model's TPM/RPM limits by querying Groq API.
    Returns (max_rpm, max_tpm) or (None, None) if detection fails.
    """
    try:
        print(f"\n{colored('[SCAN] Detecting model limits from Groq API...', Colors.CYAN)}")
        
        # Try to get model info from Groq API
        # Note: Groq doesn't have a dedicated models endpoint, so we'll make a minimal test call
        # and check the rate limit headers in the response
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1
            },
            timeout=10
        )
        
        # DEBUG: Print ALL headers to see exact naming
        headers = response.headers
        print(f"\n{colored('? DEBUG: ALL RESPONSE HEADERS', Colors.YELLOW)}")
        print(f"{colored('=' * 70, Colors.YELLOW)}")
        for key, value in headers.items():
            if 'rate' in key.lower() or 'limit' in key.lower():
                print(f"{colored(f'{key}: {value}', Colors.YELLOW)}")
        print(f"{colored('=' * 70, Colors.YELLOW)}\n")
        
        max_rpm = None
        max_tpm = None
        
        # Groq API headers (based on actual API response):
        # x-ratelimit-limit-requests: RPD (Requests Per Day) - e.g., 500000
        # x-ratelimit-limit-requests-minute: RPM (Requests Per Minute) - e.g., 1000
        # x-ratelimit-limit-tokens: TPM (Tokens Per Minute) - e.g., 300000
        
        # Search for RPM header (must contain "minute" to avoid RPD confusion)
        for key, value in headers.items():
            key_lower = key.lower()
            # Look for headers with "ratelimit", "request", "limit", AND "minute"
            if 'ratelimit' in key_lower and 'request' in key_lower and 'limit' in key_lower and 'minute' in key_lower:
                try:
                    max_rpm = int(value)
                    print(f"{colored(f'   [OK] Found RPM header: {key} = {max_rpm}', Colors.GREEN)}")
                    break
                except ValueError:
                    pass
        
        # If no "minute" header found, fall back to checking for RPD and warn user
        if not max_rpm:
            for key, value in headers.items():
                key_lower = key.lower()
                if 'ratelimit' in key_lower and 'request' in key_lower and 'limit' in key_lower:
                    try:
                        rpd_value = int(value)
                        print(f"{colored(f'   [WARN]  Found RPD (Requests Per Day) header: {key} = {rpd_value:,}', Colors.YELLOW)}")
                        print(f"{colored(f'   [WARN]  No RPM (Requests Per Minute) header found', Colors.YELLOW)}")
                        print(f"{colored(f'   [WARN]  Estimating RPM as RPD / 1440 (minutes per day)', Colors.YELLOW)}")
                        max_rpm = rpd_value // 1440  # Rough estimate: RPD / minutes per day
                        print(f"{colored(f'   [RESULTS] Estimated RPM: {max_rpm}', Colors.CYAN)}")
                        break
                    except ValueError:
                        pass
        
        # Search for TPM header
        for key, value in headers.items():
            key_lower = key.lower()
            if 'ratelimit' in key_lower and 'token' in key_lower and 'limit' in key_lower:
                try:
                    max_tpm = int(value)
                    print(f"{colored(f'   [OK] Found TPM header: {key} = {max_tpm:,}', Colors.GREEN)}")
                    break
                except ValueError:
                    pass
        
        if max_rpm and max_tpm:
            print(f"{colored(f'[OK] Detected from API: Max RPM: {max_rpm} | Max TPM: {max_tpm:,}', Colors.GREEN)}")
            
            # Show if this is an upgraded account
            if max_tpm >= 500000:
                print(f"{colored(f'>>> UPGRADED ACCOUNT! You have {max_tpm:,} TPM', Colors.GREEN)}")
            
            return max_rpm, max_tpm
        else:
            print(f"{colored('[WARN]  Could not detect limits from API headers', Colors.YELLOW)}")
            
            # Debug: Print all headers to help troubleshoot
            print(f"{colored('   Available rate-limit headers:', Colors.DIM)}")
            for key in headers.keys():
                if 'rate' in key.lower() or 'limit' in key.lower():
                    print(f"{colored(f'   - {key}: {headers[key]}', Colors.DIM)}")
            
            return None, None
            
    except Exception as e:
        print(f"{colored(f'[WARN]  API detection failed: {str(e)[:50]}', Colors.YELLOW)}")
        return None, None

def select_model(api_key: str) -> Tuple[str, str, int, int]:
    """Interactive model selection with automatic TPM detection"""
    print(f"\n{colored('[RESULTS] Available Models:', Colors.CYAN)}")
    for key, model_info in GROQ_MODELS.items():
        print(f"  {key}. {model_info['display']}")
        if model_info['max_rpm'] and model_info['max_tpm']:
            print(f"     Max RPM: {model_info['max_rpm']} | Max TPM: {model_info['max_tpm']}")
        else:
            print(f"     {colored('(You will enter TPM manually)', Colors.DIM)}")
    
    choice = input(f"\n{colored('Select model (1, 2, or 3): ', Colors.YELLOW)}")
    
    if choice not in GROQ_MODELS:
        print(f"{colored('[ERROR] Invalid choice', Colors.RED)}")
        sys.exit(1)
    
    model_info = GROQ_MODELS[choice]
    
    # Handle custom model with manual TPM entry
    if choice == "3":
        print(f"\n{colored('? Custom Model Configuration', Colors.CYAN)}")
        
        # Get model name
        model_name = input(f"{colored('Enter model name (e.g., meta-llama/llama-4-scout-17b-16e-instruct): ', Colors.YELLOW)}").strip()
        if not model_name:
            print(f"{colored('[ERROR] Model name cannot be empty', Colors.RED)}")
            sys.exit(1)
        
        # Try to detect limits from API
        detected_rpm, detected_tpm = detect_model_limits(api_key, model_name)
        
        if detected_rpm and detected_tpm:
            # Use detected limits
            max_rpm = detected_rpm
            max_tpm = detected_tpm
            print(f"\n{colored(f'[OK] Using detected limits from API', Colors.GREEN)}")
        else:
            # Manual entry fallback
            print(f"\n{colored('[WARN]  Automatic detection failed. Please enter limits manually:', Colors.YELLOW)}")
            
            # Get TPM
            while True:
                tpm_input = input(f"{colored('Enter Max TPM (tokens per minute, e.g., 500000): ', Colors.YELLOW)}").strip()
                try:
                    max_tpm = int(tpm_input)
                    if max_tpm <= 0:
                        print(f"{colored('[ERROR] TPM must be positive', Colors.RED)}")
                        continue
                    break
                except ValueError:
                    print(f"{colored('[ERROR] Invalid number', Colors.RED)}")
            
            # Get RPM (optional, default to 30)
            rpm_input = input(f"{colored('Enter Max RPM (requests per minute, default 30): ', Colors.YELLOW)}").strip()
            if rpm_input:
                try:
                    max_rpm = int(rpm_input)
                except ValueError:
                    print(f"{colored('[WARN]  Invalid RPM, using default 30', Colors.YELLOW)}")
                    max_rpm = 30
            else:
                max_rpm = 30
        
        print(f"\n{colored(f'[OK] Custom model configured: {model_name}', Colors.GREEN)}")
        print(f"{colored(f'   Max RPM: {max_rpm} | Max TPM: {max_tpm:,}', Colors.DIM)}")
        
        return model_name, choice, max_rpm, max_tpm
    
    # For preset models (1 or 2), try to detect actual limits from API
    model_name = model_info["name"]
    default_rpm = model_info["max_rpm"]
    default_tpm = model_info["max_tpm"]
    
    model_display = model_info["display"]
    print(f"\n{colored(f'Selected: {model_display}', Colors.CYAN)}")
    print(f"{colored(f'Default limits: Max RPM: {default_rpm} | Max TPM: {default_tpm:,}', Colors.DIM)}")
    
    # Try to detect actual limits from API
    detected_rpm, detected_tpm = detect_model_limits(api_key, model_name)
    
    if detected_rpm and detected_tpm:
        # Check if detected limits are higher than defaults
        if detected_tpm > default_tpm:
            print(f"\n{colored(f'? UPGRADED LIMITS DETECTED!', Colors.GREEN)}")
            print(f"{colored(f'   Your account has: Max RPM: {detected_rpm} | Max TPM: {detected_tpm:,}', Colors.GREEN)}")
            
            use_detected = input(f"\n{colored('Use detected limits? [Y/n]: ', Colors.YELLOW)}").strip().lower()
            if use_detected != 'n':
                print(f"{colored(f'[OK] Using detected limits: {detected_tpm:,} TPM', Colors.GREEN)}")
                return model_name, choice, detected_rpm, detected_tpm
    
    # Use default limits
    print(f"{colored(f'Using default limits: {default_tpm:,} TPM', Colors.DIM)}")
    return model_name, choice, default_rpm, default_tpm

def get_codebase_path() -> str:
    """Prompt for codebase path"""
    print(f"\n{colored('? Enter path to codebase:', Colors.CYAN)}")
    path = input("? ").strip()
    
    if not Path(path).exists():
        print(f"{colored('[ERROR] Path does not exist', Colors.RED)}")
        sys.exit(1)
    
    return path

def group_files_by_extension(files: List[Path]) -> Dict[str, List[Path]]:
    """Group files by their extension"""
    grouped = {}
    for file_path in files:
        ext = file_path.suffix or ".no-ext"
        if ext not in grouped:
            grouped[ext] = []
        grouped[ext].append(file_path)
    return grouped

def estimate_total_tokens(files: List[Path]) -> int:
    """Estimate total tokens for all files (1 token ? 4 chars)"""
    total_chars = 0
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                total_chars += len(f.read())
        except Exception:
            pass
    return (total_chars // 4) + (len(files) * 500)  # Add 500 tokens per file for overhead

def print_confirmation_phase(files: List[Path], model_name: str, file_scores: Dict[str, int] = None) -> Tuple[bool, List[Path]]:
    """
    Display file breakdown and ask for user confirmation before audit.
    Caps audit to Top 150 highest-risk files.
    Returns (should_proceed, filtered_files)
    """
    print(f"\n{colored('=' * 60, Colors.BOLD)}")
    print(f"{colored('? AUDIT CONFIRMATION PHASE', Colors.BOLD)}")
    print(f"{colored('=' * 60, Colors.BOLD)}\n")
    
    # Cap to Top 150 files
    top_files = files[:150] if len(files) > 150 else files
    
    if len(files) > 150:
        print(f"{colored(f'[WARN]  Capping audit to Top 150 highest-risk files (from {len(files)} total)', Colors.YELLOW)}\n")
    
    # Group files by extension
    grouped = group_files_by_extension(top_files)
    
    # Sort by count (descending)
    sorted_groups = sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True)
    
    print(f"{colored('? Files by Extension (Top 150):', Colors.CYAN)}\n")
    for ext, file_list in sorted_groups:
        count = len(file_list)
        # Color code by count
        if count > 50:
            color = Colors.RED
        elif count > 25:
            color = Colors.YELLOW
        else:
            color = Colors.GREEN
        
        print(f"  {colored(f'{ext:12} {count:4} files', color)}")
    
    print()
    
    # Calculate token estimate for Top 150
    total_tokens = estimate_total_tokens(top_files)
    total_files = len(top_files)
    
    # Find highest risk score
    max_risk_score = 0
    if file_scores:
        for file_path in top_files:
            score = file_scores.get(str(file_path), 0)
            if score > max_risk_score:
                max_risk_score = score
    
    print(f"{colored(f'[RESULTS] Token Estimate: ~{total_tokens:,} tokens', Colors.CYAN)}")
    print(f"{colored(f'[STATS] Total Files: {total_files}', Colors.CYAN)}")
    print(f"{colored(f'[TARGET] Highest Risk Score: {max_risk_score}', Colors.RED)}")
    print(f"{colored(f'? Model: {model_name}', Colors.CYAN)}\n")
    
    # Gatekeeper prompt
    print(f"{colored('[WARN]  Ready to send', Colors.YELLOW)} {colored(f'{total_files}', Colors.BOLD)} {colored('files (~', Colors.YELLOW)}{colored(f'{total_tokens:,}', Colors.BOLD)} {colored('tokens) to Groq.', Colors.YELLOW)}")
    
    response = input(f"\n{colored('Proceed with audit? [y/N]: ', Colors.YELLOW)}")
    
    if response.lower() == 'y':
        print(f"\n{colored('[OK] Audit confirmed. Starting surgical strike...', Colors.GREEN)}\n")
        return True, top_files
    else:
        print(f"\n{colored('[ERROR] Audit cancelled by user.', Colors.RED)}")
        return False, []

def print_results(client: GroqAuditClient, results: List[Dict], layer1_skipped: int = 0):
    """Print formatted results"""
    print(f"\n{colored('=' * 60, Colors.BOLD)}")
    print(f"{colored('[RESULTS] AUDIT RESULTS', Colors.BOLD)}")
    print(f"{colored('=' * 60, Colors.BOLD)}\n")
    
    safe_count = sum(1 for r in results if r.get("status") == "safe")
    vulnerable_count = sum(1 for r in results if r.get("status") == "vulnerable")
    error_count = sum(1 for r in results if r.get("status") == "error")
    skipped_count = sum(1 for r in results if r.get("status") == "skipped") + layer1_skipped
    
    print(f"{colored(f'? Safe: {safe_count}', Colors.GREEN)}")
    print(f"{colored(f'? Vulnerable: {vulnerable_count}', Colors.YELLOW)}")
    print(f"{colored(f'[SKIP] Skipped (Layer 1): {skipped_count}', Colors.DIM)}")
    print(f"{colored(f'? Errors: {error_count}', Colors.RED)}")
    print(f"{colored(f'[STATS] Total Tokens Used: {client.total_tokens:,}', Colors.CYAN)}\n")
    
    if client.vulnerabilities_found:
        print(f"{colored('? VULNERABILITIES FOUND:', Colors.RED)}\n")
        for vuln in client.vulnerabilities_found:
            file_path = vuln["file"]
            summary = vuln.get("summary", vuln.get("finding", "Unknown vulnerability"))
            severity = vuln.get("severity", "UNKNOWN")
            vuln_type = vuln.get("type", "Unknown")
            line = vuln.get("line", "Unknown")
            
            print(f"{colored(f'? {file_path}', Colors.YELLOW)}")
            print(f"{colored(f'   {summary}', Colors.RED)}")
            print()
    
    # Latency stats
    latencies = [r.get("latency", 0) for r in results if r.get("latency") and r.get("status") != "skipped"]
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        print(f"{colored(f'[TIME]  Avg Latency: {avg_latency:.2f}s | Max: {max_latency:.2f}s', Colors.DIM)}")
    
    # Ghost-to-Star Banner
    print(f"\n{colored('=' * 60, Colors.BOLD)}")
    print(f"{colored('[*] Like the results? Support the project on GitHub:', Colors.YELLOW)}")
    print(f"{colored('https://github.com/EthanBaron/Trepan', Colors.YELLOW)}")
    print(f"{colored('=' * 60, Colors.BOLD)}\n")

def print_ground_truth(scanner: CodebaseScanner, client: GroqAuditClient, results: List[Dict]):
    """Evaluate performance against the Final_Test ground truth"""
    if "Final_Test" not in scanner.codebase_path.parts:
        return []
        
    print(f"\n{colored('=' * 60, Colors.BOLD)}")
    print(f"{colored('?? GROUND TRUTH EVALUATION (TEST SUITE ONLY)', Colors.BOLD)}")
    print(f"{colored('=' * 60, Colors.BOLD)}")
    
    target_vulnerable = []
    skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build', '.next', 'out', 'coverage'}
    for ext in scanner.extensions:
        pattern = f"**/*{ext}"
        for file_path in scanner.codebase_path.glob(pattern):
            if any(skip_dir in file_path.parts for skip_dir in skip_dirs):
                continue
            if "_secure" not in file_path.name:
                target_vulnerable.append(file_path)
    
    caught_paths = [Path(v["file"]).name for v in client.vulnerabilities_found]
    missed_files = []
    
    for tv in target_vulnerable:
        if tv.name not in caught_paths:
            skipped_paths = {p[0].name: p[1] for p in scanner.skipped_files}
            
            if tv.name in skipped_paths:
                missed_files.append((tv, "[Layer 1 Blindspot]", f"({skipped_paths[tv.name]})"))
            else:
                file_status = "Unknown"
                for r in results:
                    if Path(r["file"]).name == tv.name:
                        file_status = r["status"]
                        break
                
                if file_status == "safe":
                    missed_files.append((tv, "[LLM False Negative]", "(Marked SAFE by Groq)"))
                elif file_status == "error":
                    missed_files.append((tv, "[LLM Error]", "(API Error / Timeout)"))
                elif file_status == "skipped":
                    missed_files.append((tv, "[Token Limit Skip]", "(File too large / Token limit)"))
                else:
                    missed_files.append((tv, f"[Unknown Status: {file_status}]", ""))
                    
    print(f"[TARGET] Target Vulnerable Files: {len(target_vulnerable)}")
    print(f"[OK] Successfully Caught: {len([tv for tv in target_vulnerable if tv.name in caught_paths])}")
    
    print(f"\n[ERROR] MISSED FILES ({len(missed_files)}):")
    for file_path, root_cause, detail in missed_files:
        print(f"- {file_path.name} -> WHY: {root_cause} {detail}")
        
    return missed_files

async def run_autopsy(client: GroqAuditClient, missed_files: List[Tuple[Path, str, str]]):
    """Diagnose why files were missed"""
    if not missed_files:
        return
        
    for file_path, root_cause, detail in missed_files:
        print(f"\n{colored('[SCAN] AUTOPSY REPORT:', Colors.HEADER)}")
        print(f"{colored(f'Analyzing missed file: {file_path.name}...', Colors.CYAN)}")
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                code = f.read()
                
            system_prompt = (
                "You are the Chief Architect of the Trepan Security Engine.\n"
                "Our engine just failed to detect a vulnerability in the provided code file.\n"
                "Your job is to tell us WHY we missed it.\n"
                "Did our Layer 1 AST/Regex fail to spot the Risk Surface? Or did our Layer 2 System Prompt fail to classify it as dangerous?\n"
                "Provide a 2-sentence explanation and suggest ONE exact regex pattern or prompt rule we should add to our engine to catch this in the future."
            )
            
            print(f"{colored('[BRAIN] Thinking...', Colors.DIM)}")
            
            response = await asyncio.to_thread(
                requests.post,
                client.endpoint,
                headers={
                    "Authorization": f"Bearer {client.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": client.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Analyze this missed file:\n\n{code}"}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 500
                },
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                diagnosis = data["choices"][0]["message"]["content"].strip()
                print(f"{colored('[TIP] AI DIAGNOSIS:', Colors.YELLOW)}\n{diagnosis}\n")
            else:
                print(f"{colored('[TIP] AI DIAGNOSIS: [API Error/Rate Limit during Autopsy]', Colors.RED)}\n")
                
        except Exception as e:
            print(f"{colored(f'[TIP] AI DIAGNOSIS: [Local Error during Autopsy: {str(e)}]', Colors.RED)}\n")

# --- Main -------------------------------------------------------------------

async def main():
    print_header()
    
    # -- TASK 0: INTERACTIVE EXECUTION MODE (MANDATORY) ----------------------
    print(f"\n{colored('? TREPAN SELF-VALIDATION SYSTEM', Colors.BOLD)}")
    print(f"{colored('=' * 60, Colors.BOLD)}\n")
    
    print("Select Mode:")
    print("  1. Run Internal Test Suite (Recommended)")
    print("  2. Continue to Full Audit\n")
    
    mode_choice = input(f"{colored('Enter choice (1/2): ', Colors.YELLOW)}")
    
    if mode_choice == "1":
        # Import sanity tests
        from trepan_server.sanity_tests import run_internal_sanity_tests
        
        # Run tests without LLM (AST-only for now)
        test_results, all_passed = run_internal_sanity_tests(llm_analyzer_func=None)
        
        if not all_passed:
            print(f"\n{colored('[CRITICAL] CALIBRATION ERROR: Auditor is unreliable. Aborting scan.', Colors.RED)}")
            sys.exit(1)
        
        print(f"{colored('[OK] All sanity tests passed! System is calibrated.', Colors.GREEN)}\n")
    
    elif mode_choice != "2":
        print(f"{colored('[ERROR] Invalid choice. Exiting.', Colors.RED)}")
        sys.exit(1)
    
    # -- CONTINUE TO FULL AUDIT ----------------------------------------------
    
    # Get configuration
    api_key = get_api_key()
    model_name, model_choice, max_rpm, max_tpm = select_model(api_key)
    codebase_path = get_codebase_path()
    
    # File extensions to scan
    extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rb', '.php', '.cs', '.json']
    
    # Initialize components
    rate_limiter = TokenBucket(max_rpm, max_tpm)
    scanner = CodebaseScanner(codebase_path, extensions, max_size_kb=500)
    client = GroqAuditClient(api_key, model_name, rate_limiter)
    
    # Scan codebase (Layer1PreScreener applied during scan, files sorted by risk score)
    files = scanner.scan()
    if not files:
        print(f"{colored('[ERROR] No auditable files found after filtering', Colors.RED)}")
        sys.exit(1)
    
    # Show confirmation phase with breakdown and Top 50 cap
    should_proceed, filtered_files = print_confirmation_phase(files, model_name, scanner.file_scores)
    if not should_proceed:
        sys.exit(0)
    
    # Start audit timer
    audit_start_time = time.time()
    
    # Run audit on filtered files (concurrency=2 for aggressive error suppression)
    results = await client.audit_codebase(filtered_files, concurrency=2)
    
    # Calculate audit duration
    audit_end_time = time.time()
    audit_duration = audit_end_time - audit_start_time
    
    # Print results
    print_results(client, results, len(scanner.skipped_files))
    
    # Print audit timing
    hours = int(audit_duration // 3600)
    minutes = int((audit_duration % 3600) // 60)
    seconds = int(audit_duration % 60)
    
    if hours > 0:
        time_str = f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        time_str = f"{minutes}m {seconds}s"
    else:
        time_str = f"{seconds}s"
    
    print(f"{colored('[TIME]  Audit Duration: ', Colors.CYAN)}{colored(time_str, Colors.BOLD)}")
    
    # Ground Truth Evaluator
    missed = print_ground_truth(scanner, client, results)
    
    if missed:
        await run_autopsy(client, missed)
    
    print(f"\n{colored('[OK] Stress test complete!', Colors.GREEN)}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{colored('[WARN]  Audit interrupted by user', Colors.YELLOW)}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{colored(f'[ERROR] Error: {str(e)}', Colors.RED)}")
        sys.exit(1)
