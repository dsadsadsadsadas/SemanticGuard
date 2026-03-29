#!/usr/bin/env python3
"""
🛡️ SemanticGuard Gatekeeper — FastAPI Server
POST /evaluate  → drift evaluation using llama3.1:8b
GET  /health    → status + model loaded flag
"""

# Force UTF-8 output on Windows to prevent charmap codec crashes with emoji characters
import sys, io
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    from . import sink_registry
except ImportError:
    import sink_registry

import logging
import time
import os
import shutil
import difflib
import hashlib
import re
import json
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Tuple, Any, Union

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Add Rule Sanctuary path detection function
def is_semanticguard_path(file_path: str) -> bool:
    """
    Robust path analysis to detect .semanticguard/ folder paths.
    Uses proper path parsing with os.path.normpath() for cross-platform compatibility.

    Args:
        file_path: The file path to analyze (can be relative or absolute)

    Returns:
        bool: True if the path is within a .semanticguard/ folder, False otherwise
    """
    if not file_path:
        return False

    # Normalize the path for cross-platform compatibility
    normalized_path = os.path.normpath(file_path)

    # Split the path into components
    path_parts = normalized_path.split(os.path.sep)

    # Check if any part of the path is ".semanticguard"
    return ".semanticguard" in path_parts

# Handle both relative and absolute imports for flexibility
try:
    from .prompt_builder import (
        build_prompt, 
        build_meta_gate_prompt, 
        extract_data_flow_spec, 
        STRUCTURAL_INTEGRITY_SYSTEM, 
        STRUCTURAL_INTEGRITY_SYSTEM_LLAMA, 
        METAGATE_AUDIT_SYSTEM, 
        get_hardened_system_prompt, 
        get_drift_detection_prompt
    )
    from .response_parser import guillotine_parser
    from .model_loader import get_model, generate
except (ImportError, ValueError):
    # Fallback for when running directly (not as a package)
    import sys
    _dir = os.path.dirname(os.path.abspath(__file__))
    if _dir not in sys.path:
        sys.path.append(_dir)
    from prompt_builder import (
        build_prompt, 
        build_meta_gate_prompt, 
        extract_data_flow_spec, 
        STRUCTURAL_INTEGRITY_SYSTEM, 
        STRUCTURAL_INTEGRITY_SYSTEM_LLAMA, 
        METAGATE_AUDIT_SYSTEM, 
        get_hardened_system_prompt, 
        get_drift_detection_prompt
    )
    from response_parser import guillotine_parser
    from model_loader import get_model, generate

# Import TokenBucket for cloud rate limiting
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'st'))
from token_bucket import TokenBucket
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("semanticguard.server")

# ─── Cross-Platform Path Resolver ─────────────────────────────────────────────

def get_root_dir() -> str:
    """
    Returns the absolute path to the project root directory.
    Dynamically resolved relative to this file so it works across Windows, macOS, Linux, and WSL 
    without any hardcoded paths.
    """
    # This file is in semanticguard_server/server.py
    # The project root is one level up.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── Configuration Exclusions ──────────────────────────────────────────────────
# Keys that should never be audited to prevent over-policing of settings/metadata.
SILENT_EXCLUSIONS = [
    "semanticguard.processor_mode", 
    "semanticguard.enabled",
    "semanticguard.serverUrl",
    "editor.fontSize", 
    "editor.fontFamily",
    "workbench.colorTheme"
]

# ─── Layer 1 Pre-Screener (Migrated from stress_test.py) ──────────────────

class CloudLayer1PreScreener:
    """
    Exploitability-Based Security Filtering.
    Analyzes execution control surfaces and environment variable injection.
    Reduces false positives by focusing on real attack paths.
    
    Migrated from st/stress_test.py for cloud evaluation endpoint.
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
        "eval_with_input": r"eval\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.|expr|formula|input|data)",
        "exec_with_input": r"exec\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.|expr|formula|input|data)",
        "os_system_with_input": r"os\.system\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)",
        "env_injection": r"(?:LD_PRELOAD|BASH_ENV|ZDOTDIR|PYTHONPATH|NODE_OPTIONS)\s*:\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)",
        "zip_slip": r"(?i)(zipfile|ZipFile|tarfile|extractall|extract\()",
        "deserialization": r"(?i)(yaml\.load\(|pickle\.loads\()",
        "prototype_pollution_sink": r"(?i)(__proto__|prototype|Object\.assign\()",
        "open_redirect_sink": r"(?i)(window\.location|res\.redirect\()",
        "insecure_config": r"debug\s*=\s*True",
        "file_upload_risk": r"(?i)(mimetype|file_upload)",
        "ssh_injection": r"exec_command",
    }
    
    # SYSTEM KEYWORDS: +2 pts each (Risk Surface Detection)
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
    def _is_hard_skip_file(filename: str, code: str) -> Tuple[bool, str]:
        """Check if file should be hard-skipped (test, style, etc.)"""
        filename_lower = filename.lower()
        
        # Check hard skip patterns
        for pattern_name, pattern in CloudLayer1PreScreener.HARD_SKIP_PATTERNS.items():
            if re.search(pattern, filename_lower):
                return True, f"Hard skip: {pattern_name}"
        
        # Check safe filename keywords
        for keyword_type, pattern in CloudLayer1PreScreener.SAFE_FILENAME_KEYWORDS.items():
            if re.search(pattern, filename_lower):
                return True, f"Hard skip: {keyword_type} in filename"
        
        # Check safe content keywords (quick scan)
        for keyword_type, pattern in CloudLayer1PreScreener.SAFE_CONTENT_KEYWORDS.items():
            if re.search(pattern, code[:2000]):  # Only scan first 2KB
                return True, f"Hard skip: {keyword_type} in content"
        
        return False, ""
    
    SECRET_KEYWORDS = {
        "secret": r"(?i)secret",
        "password": r"(?i)password",
        "api_key": r"(?i)api_key",
        "token": r"(?i)token",
        "credentials": r"(?i)credentials",
        "stripe": r"(?i)stripe",
        "aws": r"(?i)aws"
    }

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
        for keyword_name, pattern in CloudLayer1PreScreener.EXPLOITABILITY_KEYWORDS.items():
            matches = len(re.findall(pattern, code))
            score += matches * 5
        
        # Count sensitive keywords (FORCE PASS)
        for keyword_name, pattern in CloudLayer1PreScreener.SECRET_KEYWORDS.items():
            matches = len(re.findall(pattern, code))
            score += matches * 5
            
        # Count system keywords (needs context)
        for keyword_name, pattern in CloudLayer1PreScreener.SYSTEM_KEYWORDS.items():
            matches = len(re.findall(pattern, code))
            score += matches * 2
        
        # Apply UI penalties
        for keyword_name, pattern in CloudLayer1PreScreener.UI_PENALTIES.items():
            matches = len(re.findall(pattern, code))
            score -= matches * 3
        
        # Ensure score doesn't go below 0
        return max(0, score)
    
    @staticmethod
    def should_audit(code: str, file_extension: str, filename: str = "") -> Tuple[bool, str, int]:
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
        if filename:
            is_skip, reason = CloudLayer1PreScreener._is_hard_skip_file(filename, code)
            if is_skip:
                return False, reason, 0
        
        # Calculate risk score (exploitability-based)
        risk_score = CloudLayer1PreScreener.calculate_risk_score(code)
        
        # POSITIVE FILTER: must have at least ONE exploitable keyword or risk signals (score >= 2)
        if risk_score >= 2:
            return True, f"Exploitability score: {risk_score}", risk_score
        
        # Default: skip (no exploitable patterns found)
        return False, "No exploitable attack paths detected", 0

def clean_code_snippet(filename: str, code: str) -> str:
    """
    Strips 'Silent Exclusions' from JSON content to prevent LLM noise/drift.
    """
    if not (filename.endswith(".json") or filename.endswith(".jsonc")):
        return code
        
    try:
        import json
        # Handle simple JSON (standard)
        data = json.loads(code)
        
        def recursive_strip(obj):
            if isinstance(obj, dict):
                return {k: recursive_strip(v) for k, v in obj.items() if k not in SILENT_EXCLUSIONS}
            elif isinstance(obj, list):
                return [recursive_strip(x) for x in obj]
            return obj
            
        cleaned = recursive_strip(data)
        return json.dumps(cleaned, indent=2)
    except Exception as e:
        # If parsing fails (e.g. invalid JSON or JSONC with comments), 
        # fallback to a simpler regex-based line stripper for the excluded keys.
        import re
        lines = code.splitlines()
        filtered_lines = []
        for line in lines:
            # Match "key": value or "key" : value
            found_exclusion = False
            for key in SILENT_EXCLUSIONS:
                if re.search(f'"{re.escape(key)}"\s*:', line):
                    found_exclusion = True
                    break
            if not found_exclusion:
                filtered_lines.append(line)
        return "\n".join(filtered_lines)

# ─── Vault Synchronization ─────────────────────────────────────────────────────

# ─── Diagnostic Trace Logger (ssart_trace_sync.log) ─────────────────────────
_trace_sync_logger = logging.getLogger("semanticguard.trace_sync")
_trace_sync_logger.setLevel(logging.DEBUG)

# Use absolute path to ensure log is found in the project root
try:
    _log_path = os.path.join(get_root_dir(), "ssart_trace_sync.log")
    _trace_handler = logging.FileHandler(_log_path, encoding="utf-8")
    _trace_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    _trace_sync_logger.addHandler(_trace_handler)
except Exception as e:
    print(f"WARNING: Failed to initialize trace logger at root: {e}")
    # Fallback to local
    _trace_handler = logging.FileHandler("ssart_trace_sync.log", encoding="utf-8")
    _trace_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    _trace_sync_logger.addHandler(_trace_handler)

_trace_sync_logger.propagate = False  # Don't duplicate to console

# ─── Vault Initialization ───────────────────────────────────────────────────

VAULT_STATE = {}
PILLARS = [
    "golden_state.md",
    "done_tasks.md",
    "pending_tasks.md",
    "history_phases.md",
    "system_rules.md",
    "problems_and_resolutions.md",
]

# ─── Golden Templates ────────────────────────────────────────────────────────

GOLDEN_TEMPLATES = {
    "solo-indie": {
        "name": "Solo-Indie (The Speedster)",
        "description": "For solo developers who need readable, maintainable code without over-engineering",
        "system_rules": """# Solo-Indie System Rules (The Speedster)

## Core Philosophy
Keep it simple, keep it readable. You're flying solo, so future-you needs to understand what present-you wrote.

## Rule 1: Function Size Limit
- NO functions longer than 50 lines
- If a function does more than one thing, split it
- Each function should have a single, clear purpose

## Rule 2: Nesting Depth Limit
- Maximum 3 levels of nesting (if/for/while)
- Deeply nested code is a code smell - refactor it
- Use early returns to reduce nesting

## Rule 3: Naming Clarity
- Variable names must be descriptive (no single letters except loop counters)
- Function names must be verbs (getUserData, calculateTotal, validateInput)
- Class names must be nouns (User, DataProcessor, ValidationEngine)

## Rule 4: Comment the Why, Not the What
- Don't comment obvious code
- DO comment complex business logic
- DO comment workarounds and edge cases

## Rule 5: DRY (Don't Repeat Yourself)
- If you copy-paste code more than twice, make it a function
- Shared logic belongs in utility modules
- Configuration belongs in config files, not scattered in code

## Rule 6: Error Handling
- Always handle errors explicitly
- No silent failures
- Log errors with context (what failed, why, when)

## Rule 7: Test the Critical Path
- Write tests for business logic
- Write tests for edge cases
- Don't test trivial getters/setters

## Core Security Rules (RULE_100-110)

### RULE_100: HARDCODED_SECRETS
- NO hardcoded secrets, API keys, passwords, or tokens in code
- Use environment variables or secret management services
- Secrets must never appear in logs or error messages
- Action: REJECT if any hardcoded credentials detected

### RULE_101: EVAL_INJECTION
- NO `eval()` or `exec()` with any input (user or otherwise)
- These functions execute arbitrary code and are inherently dangerous
- Action: REJECT if eval/exec detected

### RULE_102: SHELL_INJECTION
- NO `os.system()` or `subprocess` with `shell=True`
- Use argument lists instead of shell strings
- Action: REJECT if shell=True detected

### RULE_103: SQL_INJECTION
- ALL SQL queries must use parameterized statements
- NO string concatenation or f-strings in SQL
- Action: REJECT if dynamic SQL detected

### RULE_104: PHI_PROTECTION
- Sensitive data (SSN, credit card, medical info, PII) must NOT reach insecure sinks
- Insecure sinks: print(), console.log(), logs, unencrypted HTTP responses
- Action: REJECT if sensitive data flows to insecure sink

### RULE_105: LOGGING_GATE
- NO sensitive data in logs without sanitization
- Passwords, tokens, credit cards must be redacted
- Action: REJECT if sensitive data logged

## Rule 11: Multi-Hop Taint Analysis with Static Content Check

**Step 0 — Static Dangerous Content Check (Pre-Taint):** Before tracing any data flow, scan for hardcoded dangerous values that are dangerous regardless of their source:
- Any hardcoded string containing `<script>`, `javascript:`, `onerror=`, `onload=`, or HTML event handlers
- Any hardcoded string passed directly to `innerHTML`, `document.write()`, or `eval()`
- Any hardcoded string that IS the payload (not a sanitized output, but a raw attack string)

These are CRITICAL findings even if no runtime user input is involved. A hardcoded XSS payload is still an XSS payload.

1. **Identify the Sink:** Locate any function that executes commands, queries, or renders raw HTML.
2. **Trace Backward:** Trace variables backward through all function calls and class instantiations.
3. **Identify the Source:** Did this data originate from an untrusted source?
4. **Check for Sanitization:** Was the data explicitly sanitized between Source and Sink?
5. **The Verdict:** If untrusted data flows to a dangerous sink without sanitization, flag as CRITICAL.
""",
        "llm_prompt": """Generate a 'Perfect Execution' code example for the Solo-Indie (Speedster) mode.

Requirements:
- Show a simple, readable function that follows all Solo-Indie rules
- Maximum 50 lines
- Maximum 3 levels of nesting
- Clear naming
- Proper error handling
- Include comments explaining the 'why'
- Use Python as the language

Output ONLY the code example with a brief introduction. No extra commentary."""
    },
    "clean-layers": {
        "name": "Clean-Layers (The Architect)",
        "description": "For serious, long-term projects that need strict separation of concerns",
        "system_rules": """# Clean-Layers System Rules (The Architect)

## Core Philosophy
Separation of concerns is law. The Brain (logic) and Body (UI) must never mix. This is architecture for the long haul.

## Rule 1: Strict Layer Separation
- **Presentation Layer**: UI components only, no business logic
- **Business Logic Layer**: Pure logic, no UI dependencies
- **Data Access Layer**: Database/API calls only, no business logic
- NEVER import UI code into business logic
- NEVER put business logic in UI components

## Rule 2: Dependency Direction
- Outer layers depend on inner layers, NEVER the reverse
- UI depends on Business Logic
- Business Logic depends on Data Access
- Data Access depends on nothing (except external services)

## Rule 3: Interface Contracts
- All layer boundaries must have explicit interfaces/protocols
- Business logic exposes interfaces, UI implements them
- Data access exposes repositories, business logic uses them
- Changes to one layer should not break others

## Rule 4: Single Responsibility Principle
- Each class/module has ONE reason to change
- If a class does multiple things, split it
- God objects are forbidden

## Rule 5: Dependency Injection
- Dependencies must be injected, not instantiated
- Use constructor injection for required dependencies
- Use setter injection for optional dependencies
- Makes testing and swapping implementations trivial

## Rule 6: Pure Functions Where Possible
- Business logic should prefer pure functions (same input = same output)
- Side effects (I/O, state changes) should be isolated
- Pure functions are easier to test and reason about

## Rule 7: Configuration Over Code
- Environment-specific values go in config files
- Feature flags for conditional behavior
- NO hardcoded URLs, paths, or credentials

## Rule 8: API Design
- RESTful endpoints follow standard conventions
- Consistent error response format
- Versioned APIs (/v1/, /v2/)
- OpenAPI/Swagger documentation required

## Core Security Rules (RULE_100-110)

### RULE_100: HARDCODED_SECRETS
- NO hardcoded secrets, API keys, passwords, or tokens in code
- Use environment variables or secret management services
- Secrets must never appear in logs or error messages
- Action: REJECT if any hardcoded credentials detected

### RULE_101: EVAL_INJECTION
- NO `eval()` or `exec()` with any input (user or otherwise)
- These functions execute arbitrary code and are inherently dangerous
- Action: REJECT if eval/exec detected

### RULE_102: SHELL_INJECTION
- NO `os.system()` or `subprocess` with `shell=True`
- Use argument lists instead of shell strings
- Action: REJECT if shell=True detected

### RULE_103: SQL_INJECTION
- ALL SQL queries must use parameterized statements
- NO string concatenation or f-strings in SQL
- Action: REJECT if dynamic SQL detected

### RULE_104: PHI_PROTECTION
- Sensitive data (SSN, credit card, medical info, PII) must NOT reach insecure sinks
- Insecure sinks: print(), console.log(), logs, unencrypted HTTP responses
- Action: REJECT if sensitive data flows to insecure sink

### RULE_105: LOGGING_GATE
- NO sensitive data in logs without sanitization
- Passwords, tokens, credit cards must be redacted
- Action: REJECT if sensitive data logged

## Rule 11: Multi-Hop Taint Analysis with Static Content Check

**Step 0 — Static Dangerous Content Check (Pre-Taint):** Before tracing any data flow, scan for hardcoded dangerous values that are dangerous regardless of their source:
- Any hardcoded string containing `<script>`, `javascript:`, `onerror=`, `onload=`, or HTML event handlers
- Any hardcoded string passed directly to `innerHTML`, `document.write()`, or `eval()`
- Any hardcoded string that IS the payload (not a sanitized output, but a raw attack string)

These are CRITICAL findings even if no runtime user input is involved. A hardcoded XSS payload is still an XSS payload.

1. **Identify the Sink:** Locate any function that executes commands, queries, or renders raw HTML.
2. **Trace Backward:** Trace variables backward through all function calls and class instantiations.
3. **Identify the Source:** Did this data originate from an untrusted source?
4. **Check for Sanitization:** Was the data explicitly sanitized between Source and Sink?
5. **The Verdict:** If untrusted data flows to a dangerous sink without sanitization, flag as CRITICAL.
""",
        "llm_prompt": """Generate a 'Perfect Execution' code example for the Clean-Layers (Architect) mode.

Requirements:
- Show a three-layer architecture: Presentation, Business Logic, Data Access
- Demonstrate strict separation of concerns
- Show dependency injection
- Show interface contracts between layers
- Include a simple use case (e.g., user registration)
- Use Python as the language

Output ONLY the code example with a brief introduction. No extra commentary."""
    },
    "secure-stateless": {
        "name": "Secure-Stateless (The Fortress)",
        "description": "Maximum security mode - assume everyone is a hacker, prioritize privacy above all",
        "system_rules": """# Secure-Stateless System Rules (The Fortress)

## Core Philosophy
Trust no one. Assume every input is malicious. Privacy is non-negotiable. Stateless architecture prevents session hijacking.

## Rule 1: Input Sanitization (MANDATORY)
- ALL user input must be validated and sanitized
- Use allowlists, not denylists (specify what's allowed, not what's forbidden)
- Validate data type, length, format, and range
- Reject invalid input immediately with clear error messages
- NO raw user input in SQL, shell commands, or file paths

## Rule 2: Zero Trust Architecture
- Authenticate every request
- Authorize every action
- Validate every input
- Log every security event
- Assume breach - design for containment

## Rule 3: Stateless Sessions
- NO server-side session storage
- Use JWT tokens with short expiration (15 minutes max)
- Include refresh tokens for extended sessions
- Tokens must be signed and verified
- Store tokens in httpOnly cookies (not localStorage)

## Rule 4: Secrets Management
- NO hardcoded secrets ANYWHERE
- Use environment variables for secrets
- Use secret management services (Vault, AWS Secrets Manager)
- Rotate secrets regularly
- Secrets must never appear in logs or error messages

## Rule 5: Encryption Everywhere
- ALL data in transit must use TLS 1.3+
- ALL sensitive data at rest must be encrypted
- Use bcrypt/argon2 for password hashing (NEVER plain SHA/MD5)
- Use AES-256 for data encryption
- Key management must be separate from application code

## Rule 6: Principle of Least Privilege
- Services run with minimum required permissions
- Database users have minimum required grants
- API keys have minimum required scopes
- File system access is restricted to specific directories

## Rule 7: Audit Logging
- Log all authentication attempts (success and failure)
- Log all authorization failures
- Log all data access (who, what, when)
- Logs must be tamper-proof (write-only, signed)
- NO sensitive data in logs (passwords, tokens, PII)

## Rule 8: Rate Limiting & DDoS Protection
- Rate limit all public endpoints
- Implement exponential backoff for failed auth
- Use CAPTCHA for sensitive operations
- Monitor for suspicious patterns

## Rule 9: Secure Defaults
- Fail closed, not open (deny by default)
- Disable unnecessary features
- Remove debug endpoints in production
- Use security headers (CSP, HSTS, X-Frame-Options)

## Rule 10: Privacy by Design
- Collect minimum necessary data
- Anonymize data where possible
- Implement data retention policies
- Support data deletion requests (GDPR compliance)
- NO third-party tracking without explicit consent

## Core Security Rules (RULE_100-110)

### RULE_100: HARDCODED_SECRETS
- NO hardcoded secrets, API keys, passwords, or tokens in code
- Use environment variables or secret management services
- Secrets must never appear in logs or error messages
- Action: REJECT if any hardcoded credentials detected

### RULE_101: EVAL_INJECTION
- NO `eval()` or `exec()` with any input (user or otherwise)
- These functions execute arbitrary code and are inherently dangerous
- Action: REJECT if eval/exec detected

### RULE_102: SHELL_INJECTION
- NO `os.system()` or `subprocess` with `shell=True`
- Use argument lists instead of shell strings
- Action: REJECT if shell=True detected

### RULE_103: SQL_INJECTION
- ALL SQL queries must use parameterized statements
- NO string concatenation or f-strings in SQL
- Action: REJECT if dynamic SQL detected

### RULE_104: PHI_PROTECTION
- Sensitive data (SSN, credit card, medical info, PII) must NOT reach insecure sinks
- Insecure sinks: print(), console.log(), logs, unencrypted HTTP responses
- Action: REJECT if sensitive data flows to insecure sink

### RULE_105: LOGGING_GATE
- NO sensitive data in logs without sanitization
- Passwords, tokens, credit cards must be redacted
- Action: REJECT if sensitive data logged

## Mandatory Code Security (Additional)
- NO `eval()` or `exec()` EVER
- NO `os.system()` or `subprocess` with `shell=True`
- NO dynamic SQL queries (use parameterized queries ONLY)
- ALL file paths must use `os.path.realpath()` + `startswith()` validation
- NO pickle/marshal for untrusted data
- Use safe YAML/JSON parsers (no `yaml.load()`, use `yaml.safe_load()`)

## Dependency Security
- Pin all dependency versions
- Scan dependencies for vulnerabilities (npm audit, safety)
- Update dependencies regularly
- Review dependency licenses
- Minimize dependency count

## RULE_110: DOM_INTEGRITY_PROTECTION
- Forbidden use of innerHTML, outerHTML, or document.write
- Reasoning: These are primary XSS vectors
- Action: Use textContent or innerText instead
- Action: REJECT if innerHTML/outerHTML/document.write detected

## Rule 11: Multi-Hop Taint Analysis with Static Content Check

**Step 0 — Static Dangerous Content Check (Pre-Taint):** Before tracing any data flow, scan for hardcoded dangerous values that are dangerous regardless of their source:
- Any hardcoded string containing `<script>`, `javascript:`, `onerror=`, `onload=`, or HTML event handlers
- Any hardcoded string passed directly to `innerHTML`, `document.write()`, or `eval()`
- Any hardcoded string that IS the payload (not a sanitized output, but a raw attack string)

These are CRITICAL findings even if no runtime user input is involved. A hardcoded XSS payload is still an XSS payload.

1. **Identify the Sink:** Locate any function that executes commands, queries, or renders raw HTML.
2. **Trace Backward:** Trace variables backward through all function calls and class instantiations.
3. **Identify the Source:** Did this data originate from an untrusted source?
4. **Check for Sanitization:** Was the data explicitly sanitized between Source and Sink?
5. **The Verdict:** If untrusted data flows to a dangerous sink without sanitization, flag as CRITICAL.
""",
        "llm_prompt": """Generate a 'Perfect Execution' code example for the Secure-Stateless (Fortress) mode.

Requirements:
- Show a secure API endpoint with input validation
- Demonstrate JWT token authentication
- Show input sanitization and validation
- Show secure error handling (no information leakage)
- Include rate limiting
- Show audit logging
- Use Python/FastAPI as the language

Output ONLY the code example with a brief introduction. No extra commentary."""
    }
}

# ─── Cryptographic Vault Security ──────────────────────────────────────────

def calculate_vault_hash(root_dir: str = None) -> str:
    """
    Calculate a SHA-256 hash representing the current Vault disk state.
    
    Args:
        root_dir: Optional. Absolute path to project root. Defaults to get_root_dir().
    """
    if not root_dir:
        root_dir = get_root_dir()

    hasher = hashlib.sha256()
    vault_dir = os.path.join(root_dir, ".semanticguard", "semanticguard_vault")
    
    if not os.path.exists(vault_dir):
        return ""

    for pillar in sorted(PILLARS):
        dst = os.path.join(vault_dir, pillar)
        if os.path.exists(dst):
            with open(dst, "rb") as f:
                hasher.update(f.read())
        else:
            hasher.update(b"") 
            
    return hasher.hexdigest()

def verify_vault_hash(project_path: str = None) -> bool:
    """Check if the Vault matches the .semanticguard.lock signature."""
    root_dir = project_path if project_path else get_root_dir()
    lock_file = os.path.join(root_dir, ".semanticguard", ".semanticguard.lock")
    
    if not os.path.exists(lock_file):
        return True # If no lock exists, assume valid for first run
        
    with open(lock_file, "r", encoding="utf-8") as f:
        try:
            lock_data = json.load(f)
            stored_hash = lock_data.get("signature", "")
        except json.JSONDecodeError:
            # Fallback for old raw-text locks during transition
            f.seek(0)
            stored_hash = f.read().strip()
        
    return calculate_vault_hash(root_dir) == stored_hash  # Pass explicit root_dir

def write_vault_lock(root_dir: str = None):
    """
    Sign the vault by saving its hash to .semanticguard.lock in JSON format.
    
    Args:
        root_dir: Optional. Absolute path to project root. Defaults to get_root_dir().
    """
    if not root_dir:
        root_dir = get_root_dir()
    lock_file = os.path.join(root_dir, ".semanticguard", ".semanticguard.lock")
    
    file_hash = calculate_vault_hash(root_dir)
    
    lock_payload = {
        "signature": file_hash,
        "last_updated": time.time(),
        "status": "SECURE",
        "warning": "DO NOT EDIT. TAMPERING WILL BREAK SEMANTICGUARD SYNC."
    }
    
    with open(lock_file, "w", encoding="utf-8") as f:
        json.dump(lock_payload, f, indent=4)

def sync_and_lock_vault(filename: str, incoming_content: str, project_path: str = None) -> str:
    """
    Overwrites the vault with accepted code and re-signs the cryptographic lock.
    Includes robust OS-level error trapping for silent failure detection.
    """
    global VAULT_STATE

    # Normalize line endings to LF before storing/writing.
    # This prevents \r\r\n doubling on Windows where text-mode open()
    # auto-translates \n → \r\n, causing existing \r\n to become \r\r\n.
    incoming_content = incoming_content.replace("\r\n", "\n").replace("\r", "\n")
    
    _trace_sync_logger.info(f"SYNC START — file: {filename}, content_len: {len(incoming_content)}")
    
    # 1. Update the in-memory VAULT_STATE
    VAULT_STATE[filename] = incoming_content
    
    # 2. Write the accepted content to the correct vault snapshot file
    root_dir = project_path if project_path else get_root_dir()
    vault_dir = os.path.join(root_dir, ".semanticguard", "semanticguard_vault")
    
    try:
        os.makedirs(vault_dir, exist_ok=True)
    except PermissionError as e:
        _trace_sync_logger.critical(f"PERMISSION DENIED creating vault dir: {vault_dir} — errno={e.errno}, msg={e.strerror}")
        raise
    except OSError as e:
        _trace_sync_logger.critical(f"OS ERROR creating vault dir: {vault_dir} — errno={e.errno}, msg={e.strerror}")
        raise
    
    vault_file_path = os.path.join(vault_dir, filename)
    tmp_vault_file_path = vault_file_path + ".tmp"
    
    # 2.2 Live folder target (e.g. .semanticguard/system_rules.md)
    semanticguard_dir = os.path.join(root_dir, ".semanticguard")
    live_file_path = os.path.join(semanticguard_dir, filename)
    tmp_live_file_path = live_file_path + ".tmp"
    
    try:
        # Write in binary mode (newline=None equivalent) so Python doesn't
        # add a second \r on Windows — content is already normalized to LF.
        # 1. Update Vault Snapshot
        with open(tmp_vault_file_path, "w", encoding="utf-8", newline="") as f:
            f.write(incoming_content)
        os.replace(tmp_vault_file_path, vault_file_path)
        _trace_sync_logger.debug(f"VAULT WRITE OK — {vault_file_path}")

        # 2. Update Live Workspace Pillar
        with open(tmp_live_file_path, "w", encoding="utf-8", newline="") as f:
            f.write(incoming_content)
        os.replace(tmp_live_file_path, live_file_path)
        _trace_sync_logger.debug(f"LIVE WRITE OK — {live_file_path}")

    except PermissionError as e:
        _trace_sync_logger.critical(f"PERMISSION DENIED during bidirectional sync: {filename} — errno={e.errno}, msg={e.strerror}")
        raise
    except OSError as e:
        _trace_sync_logger.critical(f"OS ERROR during bidirectional sync: {filename} — errno={e.errno}, msg={e.strerror}")
        raise
        
    # 3. Cryptographically Lock the Vault
    try:
        write_vault_lock(root_dir)
        _trace_sync_logger.debug(f"LOCK RESIGNED OK — root: {root_dir}")
    except PermissionError as e:
        _trace_sync_logger.critical(f"PERMISSION DENIED resigning vault lock — errno={e.errno}, msg={e.strerror}")
        raise
    except OSError as e:
        _trace_sync_logger.critical(f"OS ERROR resigning vault lock — errno={e.errno}, msg={e.strerror}")
        raise
    
    # 4. Return the new signature for logging
    new_hash = calculate_vault_hash(root_dir)
    _trace_sync_logger.info(f"SYNC COMPLETE ✅ — file: {filename}, new_hash: {new_hash}")
    return new_hash


def create_default_pillars(semanticguard_dir: str):
    """
    Creates default pillar files if they don't exist.
    This ensures the 5 pillars are always present on first initialization.
    """
    print("\n[PILLAR CREATION] Checking for missing pillar files...")
    
    default_pillars = {
        "golden_state.md": """# Golden State (The Whitelist)

## 1. Mandatory Tech Stack & Versions
You MUST strictly use the following libraries. Do NOT introduce alternatives.
* **Backend Framework:** FastAPI (v0.100+)
* **Validation:** Pydantic (v2.0+)
* **Authentication:** python-jose (JWT generation only)

## 2. Approved Structural Boilerplate
When generating new files, you MUST follow this exact structure.

### [Example: API Endpoint Whitelist Structure]
```python
from fastapi import APIRouter, Depends
# ONLY use approved dependencies here

router = APIRouter()

@router.post("/endpoint")
async def standard_route(data: dict):
    # Mandatory flow: Validate -> Process -> Return
    return {"status": "success"}
```
""",
        
        "system_rules.md": """# System Rules

## Security Rules

1. NO hardcoded secrets, API keys, or passwords
2. NO `eval()` or `exec()` with user input
3. NO `os.system()` or `subprocess` with `shell=True`
4. ALL file paths must use `os.path.realpath()` + `startswith()` validation
5. ALL SQL queries must use parameterized statements

## Code Quality Rules

1. Functions should be focused and single-purpose
2. Use descriptive variable and function names
3. Comment complex logic, not obvious code
4. Handle errors explicitly - no silent failures

## Rule 11: Multi-Hop Taint Analysis (The "Source-to-Sink" Mandate)

**Context:** Modern vulnerabilities rarely happen on a single line. Developers abstract data through classes, helper functions, and state variables.

**The Directive:** When analyzing code, you MUST perform strict backward taint analysis. If you detect a dangerous execution sink (e.g., `subprocess.run`, `os.system`, `eval`, `exec`, raw SQL queries), you cannot assume the inputs are safe just because the immediate surrounding code looks benign.

**Execution Steps:**

**Step 0 — Static Dangerous Content Check (Pre-Taint):** Before tracing any data flow, scan for hardcoded dangerous values that are dangerous regardless of their source:
- Any hardcoded string containing `<script>`, `javascript:`, `onerror=`, `onload=`, or HTML event handlers
- Any hardcoded string passed directly to `innerHTML`, `document.write()`, or `eval()`
- Any hardcoded string that IS the payload (not a sanitized output, but a raw attack string)

These are CRITICAL findings even if no runtime user input is involved. A hardcoded XSS payload is still an XSS payload.

1. **Identify the Sink:** Locate any function that executes commands, queries, or renders raw HTML.
2. **Trace Backward:** Trace the variables passed into that sink backward through all function calls, class instantiations, and return values.
3. **Identify the Source:** Did this data originate from an untrusted source (e.g., `request.json`, `req.query`, `sys.argv`, file uploads)?
4. **Check for Sanitization:** Was the data explicitly sanitized, cast to a safe type, or parameterized between the Source and the Sink?
5. **The Verdict:** If the data flows from an Untrusted Source to a Dangerous Sink without explicit sanitization, you MUST flag it as a Critical Vulnerability, even if the flow crosses multiple files, classes, or functions.

## SemanticGuard System Rules

1. YOUR ARE NOT ALLOWED TO TOUCH semanticguard_vault NOR .semanticguard.lock
2. The AI must create a Walkthrough file to document its work and intent
3. Strict Contextual Synchronization: Every architectural change must align with the Project Context (README)

**Note**: Use `SemanticGuard: Initialize Project` command to generate mode-specific rules (Solo-Indie, Clean-Layers, or Secure-Stateless).
""",
        
        "done_tasks.md": """# Completed Tasks

No tasks completed yet.

## How to Use

When you complete a task from `pending_tasks.md`, move it here with a timestamp.

Example:
```
## 2024-01-15 14:30:00
- Implemented user authentication
- Added input validation
```
""",
        
        "pending_tasks.md": """# Pending Tasks

No pending tasks.

## How to Use

List your TODO items here. When completed, move them to `done_tasks.md`.

Example:
```
- [ ] Implement user authentication
- [ ] Add rate limiting to API
- [ ] Write integration tests
```
""",
        
        "history_phases.md": """# Project History

## Phase 1: Initialization
- Date: {timestamp}
- SemanticGuard initialized
- Default pillar files created

## How to Use

Document major project phases and architectural decisions here.

Example:
```
## Phase 2: Authentication System
- Date: 2024-01-15
- Implemented JWT-based authentication
- Added role-based access control
- Migrated from session-based to stateless auth
```
""".format(timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        
        "problems_and_resolutions.md": """# Problems and Resolutions

No problems reported yet.

## How to Use

Document problems you encounter and their resolutions. SemanticGuard can learn from these!

Example:
```
## Problem 1: SQL Injection Vulnerability (RESOLVED)
**Date**: 2024-01-15
**Description**: Security audit found SQL injection in user search
**Root Cause**: String concatenation in SQL queries
**Resolution**: Replaced with parameterized queries
**Status**: RESOLVED
**Pattern Learned**: NEVER use string concatenation for SQL queries
```

Use `/evolve_memory` endpoint to extract patterns from resolved problems.
"""
    }
    
    created_count = 0
    for filename, default_content in default_pillars.items():
        filepath = os.path.join(semanticguard_dir, filename)
        if not os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(default_content)
            print(f"  [CREATED] {filename}")
            created_count += 1
        else:
            print(f"  [EXISTS]  {filename}")
    
    if created_count > 0:
        print(f"[PILLAR CREATION] Created {created_count} default pillar files")
    else:
        print("[PILLAR CREATION] All pillar files already exist")


def init_vault():
    global VAULT_STATE
    try:
        print("\n" + "="*50)
        print("SHADOW VAULT INITIALIZATION STARTING...")
        
        # Target the extension testing folder explicitly
        root_dir = get_root_dir()
        semanticguard_dir = os.path.join(root_dir, ".semanticguard")
        
        # Action 2: Put semanticguard_vault INSIDE the .semanticguard folder
        vault_dir = os.path.join(semanticguard_dir, "semanticguard_vault")
        
        print(f"Target Root: {root_dir}")
        print(f"Source .semanticguard: {semanticguard_dir} (Exists? {os.path.exists(semanticguard_dir)})")
        print(f"Target Vault: {vault_dir}")
        
        os.makedirs(vault_dir, exist_ok=True)
        print(f"os.makedirs called. Vault exists on disk? {os.path.exists(vault_dir)}")
        
        # NEW: Create default pillar files if they don't exist
        create_default_pillars(semanticguard_dir)
        
        # Action: Initialize the Walkthrough Audit Ledger
        initialize_audit_ledger(semanticguard_dir)
        
        # Action: Ensure Default Rules exist in the source system_rules.md
        sys_rules_src = os.path.join(semanticguard_dir, "system_rules.md")
        if os.path.exists(sys_rules_src):
            print("\n[RULE GUARDIAN] Scanning system_rules.md for mandatory defaults...")
            with open(sys_rules_src, "r", encoding="utf-8") as f:
                raw = f.read()
            # Normalize line endings so all checks work on LF-only content
            sys_content = raw.replace("\r\n", "\n").replace("\r", "\n")

            # FIX: Never inject defaults if the section header already exists.
            # This prevents the header from being appended multiple times when
            # rule check-strings no longer match due to user edits.
            if "## SemanticGuard Mandatory Defaults" in sys_content:
                print("[RULE GUARDIAN] Mandatory defaults section already present — skipping injection.")
            else:
                mandatory_checks = [
                    ("Strict Contextual Synchronization", "Strict Contextual Synchronization. Every architectural change must logically align with the established Project Context (README). If a developer introduces a new feature, rule, or concept, they must simultaneously update all affected pillars to prevent architectural drift. Isolated updates that create a contradiction between pillars or the project's core context are strictly forbidden."),
                    ("create a Detailed And Planned Readme File", "After Understanding With User What the Project is about, create a Detailed And Planned Readme File, that is also Accepted by User."),
                    ("NO hardcoded secrets, API keys, or passwords", "NO hardcoded secrets, API keys, or passwords"),
                    ("NO `eval()` or `exec()`", "NO `eval()` or `exec()` with user input"),
                    ("NO `os.system()` or `subprocess`", "NO `os.system()` or `subprocess` with `shell=True`"),
                    ("ALL file paths must use `os.path.realpath()`", "ALL file paths must use `os.path.realpath()` + `startswith()` validation"),
                    ("ALL SQL queries must use parameterized statements", "ALL SQL queries must use parameterized statements"),
                    ("YOUR ARE NOT ALLOWED TO TOUCH semanticguard_vault NOR .semanticguard.lock", "YOUR ARE NOT ALLOWED TO TOUCH semanticguard_vault NOR .semanticguard.lock"),
                    ("Walkthrough", "The AI must create a Walkthrough file and call it Walkthrough to document its work and intent for the Validation Engine."),
                ]

                missing_rules = []
                for check_str, full_rule in mandatory_checks:
                    if check_str == "Walkthrough":
                        if "Walkthrough" in sys_content or "Rule 7" in sys_content:
                            print(f"  [OK]      Walkthrough rule already present")
                            continue
                    elif check_str in sys_content:
                        print(f"  [OK]      {check_str[:70]}")
                        continue

                    print(f"  [MISSING] {check_str[:70]}")
                    missing_rules.append(full_rule)

                if not missing_rules:
                    print("[RULE GUARDIAN] All mandatory rules are present. No injection needed.")
                else:
                    print(f"[RULE GUARDIAN] Injecting {len(missing_rules)} missing mandatory rules into system_rules.md...")

                    rule_nums = [int(n) for n in re.findall(r"(?:^|\n)Rule\s+(\d+)\s*:", sys_content, re.IGNORECASE)]
                    max_rule_num = max(rule_nums) if rule_nums else 0

                    # Write LF-only so no \r\n is introduced from append mode on Windows
                    with open(sys_rules_src, "a", encoding="utf-8", newline="") as f:
                        f.write("\n\n## SemanticGuard Mandatory Defaults\n")
                        for rule in missing_rules:
                            max_rule_num += 1
                            f.write(f"Rule {max_rule_num} : {rule}\n")
                            print(f"  [ADDED]   Rule {max_rule_num} : {rule[:70]}")
                    print(f"[RULE GUARDIAN] Done. system_rules.md now has all mandatory defaults.")
        else:
            print("[RULE GUARDIAN] No system_rules.md found — skipping rule audit.")
        
        # Action: Auto-generate the README of Truth
        initialize_project_readme(root_dir)
        
        # STRICT CHECK for all pillars existing in the vault (Ghost folder check)
        lock_file = os.path.join(semanticguard_dir, ".semanticguard.lock")
        is_first_init = not os.path.exists(lock_file)
        
        if not is_first_init:
            missing_vault_files = []
            for pillar in PILLARS:
                v_path = os.path.join(vault_dir, pillar)
                if not os.path.exists(v_path) and os.path.exists(os.path.join(semanticguard_dir, pillar)):
                    missing_vault_files.append(pillar)
            if missing_vault_files:
                print(f"🚨 [STRICT CHECK] Vault folder exists but is missing: {missing_vault_files}")
                print("🔄 Triggering FORCE_REBUILD of the Vault...")
                is_first_init = True
                
        print(f"\n[VAULT LOCK] Lock file path : {lock_file}")
        print(f"[VAULT LOCK] Lock exists     : {os.path.exists(lock_file)}")
        print(f"[VAULT LOCK] Mode            : {'FIRST INIT / REBUILD - seeding from .semanticguard/' if is_first_init else 'RESTART - loading frozen snapshot'}")
        
        copied_files = 0
        sync_differences = []

        import hashlib
        def get_md5(fpath):
            hash_md5 = hashlib.md5()
            with open(fpath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()

        for pillar in PILLARS:
            src = os.path.join(semanticguard_dir, pillar)
            dst = os.path.join(vault_dir, pillar)
            
            if is_first_init:
                # FIRST TIME / REBUILD ONLY: ATOMIC WRITE to vault
                if os.path.exists(src):
                    tmp_dst = dst + ".tmp"
                    shutil.copy2(src, tmp_dst)
                    os.replace(tmp_dst, dst)
                    copied_files += 1
            else:
                # Compare Live to Vault to detect Split Brain
                if os.path.exists(src) and os.path.exists(dst):
                    src_md5 = get_md5(src)
                    dst_md5 = get_md5(dst)
                    if src_md5 != dst_md5:
                        sync_differences.append(pillar)
                
            # Load vault into memory from the vault snapshot (not the live file)
            if os.path.exists(dst):
                with open(dst, "r", encoding="utf-8") as f:
                    VAULT_STATE[pillar] = f.read()
                if is_first_init:
                    print(f"  [VAULT] Seeded {pillar} from .semanticguard/ (Atomic Write)")
                else:
                    print(f"  [VAULT] Loaded {pillar} from snapshot ({len(VAULT_STATE[pillar])} chars)")
            else:
                VAULT_STATE[pillar] = ""
                print(f"  [VAULT] WARNING: {pillar} missing from vault (empty in VAULT_STATE)")

        if sync_differences and not is_first_init:
            print("\n" + "!"*50)
            print("🚨 SPLIT BRAIN DETECTED — AUTO-SYNCING 🚨")
            print("The following live pillars differ from the Vault:")
            for p in sync_differences:
                print(f"  - {p}")
            
            # AUTO-SYNC: Always commit live changes to the vault on startup
            for p in sync_differences:
                _src = os.path.join(semanticguard_dir, p)
                _dst = os.path.join(vault_dir, p)
                _tmp = _dst + ".tmp"
                shutil.copy2(_src, _tmp)
                os.replace(_tmp, _dst)
                print(f"  [AUTO-SYNC] ✅ Synced {p} to vault.")
                with open(_dst, "r", encoding="utf-8") as f:
                    VAULT_STATE[p] = f.read()
            write_vault_lock(root_dir)
            print("[AUTO-SYNC] ✅ Vault lock re-signed. Split brain resolved.")
            print("!"*50 + "\n")

        if is_first_init:
            print(f"\n[VAULT LOCK] First-time vault / rebuild seeded with {copied_files} files.")
            try:
                write_vault_lock(root_dir)  # Pass explicit root_dir
                print(f"[VAULT LOCK] Lock written to: {lock_file}")
                print(f"[VAULT LOCK] Lock exists now: {os.path.exists(lock_file)}")
            except Exception as lock_err:
                print(f"[VAULT LOCK] ERROR writing lock file: {lock_err}")
        else:
            print(f"\n[VAULT LOCK] Snapshot loaded ({len(VAULT_STATE)} pillars). Tripwire active.")
            print("  -> Live .semanticguard/ files are NOT copied to vault. Only ACCEPT verdicts update the vault.")
        
        print("="*50 + "\n")
        
        logger.info(f"Shadow Vault initialized at {vault_dir} and loaded into memory.")
    except Exception as e:
        print(f"\nCRITICAL ERROR IN init_vault: {e}")
        import traceback
        traceback.print_exc()
        print("="*50 + "\n")
        logger.error(f"Failed to init shadow vault: {e}")

def find_walkthrough_file(semanticguard_dir: str) -> str:
    """
    Looks for any file starting with 'walkthrough' in the .semanticguard configuration directory,
    ensuring we support generic extensions (e.g., .md, .txt) mapped by different LLMs.
    Returns path to the found file, or defaults to Walkthrough.md if none exists.
    """
    if os.path.exists(semanticguard_dir):
        for fname in os.listdir(semanticguard_dir):
            if fname.lower().startswith("walkthrough"):
                return os.path.join(semanticguard_dir, fname)
    return os.path.join(semanticguard_dir, "Walkthrough.md")

def initialize_audit_ledger(semanticguard_dir: str):
    """
    Creates Walkthrough.md (The Live Comparison Ledger) if it doesn't exist.
    It serves as a tutorial at the start, establishing the absolute 'Perfect' baseline.
    """
    ledger_path = find_walkthrough_file(semanticguard_dir)
    if not os.path.exists(ledger_path):
        ledger_name = os.path.basename(ledger_path)
        print(f"\n[LEDGER] Initializing SemanticGuard Audit Ledger ({ledger_name})...")
        template = (
            "# SemanticGuard Architectural Audit & Tutorial\n\n"
            "Welcome to SemanticGuard! This file serves as your Live Comparison Ledger.\n"
            "This file will now be updated after every execution. Compare the AI `[THOUGHT]` "
            "section below to the Absolute Solution to catch hallucinations or context drift.\n\n"
            "## Reference Architecture (The Ground Truth)\n\n"
            "This section defines the 'Perfect' baseline for SemanticGuard's reasoning. "
            "All future AI thoughts will be compared against this reference to detect drift.\n\n"
            "### Core Principles\n"
            "1. **Contextual Alignment**: Every change must align with the project's README and golden_state.md\n"
            "2. **Rule Compliance**: No violations of system_rules.md are permitted\n"
            "3. **Architectural Consistency**: Changes must maintain the established architecture\n"
            "4. **Security First**: No hardcoded secrets, unsafe eval(), or shell injection risks\n\n"
            "### Perfect Execution Example\n"
            "When SemanticGuard is thinking clearly, a perfect execution looks like this:\n"
            "```\n"
            "## 2026-01-01 12:00:00 | Result: ACCEPT\n"
            "**Thought Process:** The user is adding a new feature that aligns perfectly "
            "with the architecture defined in the golden state. The change follows established "
            "patterns, respects security rules, and maintains contextual synchronization. "
            "No rule violations detected.\n"
            "```\n\n"
            "### Hallucination Indicators\n"
            "Watch for these red flags in AI reasoning:\n"
            "- Contradictions with the README or golden_state.md\n"
            "- Ignoring explicit rules from system_rules.md\n"
            "- Introducing patterns that don't match the project architecture\n"
            "- Accepting security violations (hardcoded secrets, eval(), shell=True)\n"
            "- Vague reasoning without specific rule references\n\n"
            "---\n\n"
            "# Live Audit History\n"
            "Compare each entry below to the Reference Architecture above. "
            "Deviations indicate potential hallucinations or context drift.\n\n"
        )
        with open(ledger_path, "w", encoding="utf-8") as f:
            f.write(template)
        print(f"[LEDGER] {ledger_name} created successfully.")
    else:
        print(f"[LEDGER] {os.path.basename(ledger_path)} exists. Appending allowed.")

def initialize_project_readme(project_path: str):
    """
    Auto-generates the SemanticGuard README.md in the .semanticguard folder if it doesn't exist.
    This serves as the "README of Truth" for users.
    """
    semanticguard_dir = os.path.join(project_path, ".semanticguard")
    readme_path = os.path.join(semanticguard_dir, "README.md")
    root_readme_path = os.path.join(project_path, "README.md")
    # FORCE OVERWRITE check for 6 pillars
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            old_readme = f.read()
        if "The Six Pillars" not in old_readme:
            print(f"[README GUARDIAN] Upgrading SemanticGuard README.md to 6-Pillar Architecture...")
            os.remove(readme_path) # Force re-creation below

    if not os.path.exists(readme_path):
        print(f"\n[README GUARDIAN] Initializing SemanticGuard README.md...")
        readme_content = """# SemanticGuard: The Architectural Seatbelt 🛡️

**100% Local. Zero Cloud Leakage. Absolute Intent Verification.**

Most AI tools are "Yes-Men"—they help you write spaghetti code faster. SemanticGuard is the "No-Man." It is a local-first architectural linter designed to stop "Architecture Drift" before it hits your codebase. Built for developers who value integrity over just "vibes."

---

## 🔒 The 100% Local Promise

Your code is your most valuable asset. Why send it to the cloud?

- **Zero Cloud Leakage**: SemanticGuard runs entirely on your hardware. No AWS, no OpenAI, no metadata sent to third parties.
- **Privacy-First**: Powered by a local Llama 3.1 (8B) model via Ollama.
- **War-Room Ready**: Designed to work offline. Your security isn't dependent on an internet connection or a corporate API's uptime.

---

## 🏎️ The Architectural Seatbelt

SemanticGuard doesn't just check syntax; it enforces **Intent**.

### The Guillotine Parser
A production-hardened filter (7/7 stress tests passed) that strips away AI hallucinations and "yap," leaving only a raw ACCEPT or REJECT verdict.

### Closed-Loop Audit
Every AI decision is logged in `Walkthrough.md`. SemanticGuard "looks back" at your Reference Architecture to verify the AI isn't lying about its reasoning.

### Intent-Diff Verification
Before you commit, use the Side-by-Side Review. Compare the AI's explained "Thought" against the actual code diff to ensure the "Why" matches the "What."

---

## 🛠️ Technical Specifications

To ensure SemanticGuard's "Seatbelt" engages correctly, verify your local environment matches these production-tested specs.

### 1. The Core Engine (Ollama)
- **Model**: `llama3.1:8b` (Minimum)
- **Quantization**: `Q4_K_M` (Recommended for the best balance of speed and "Architectural Intelligence")
- **VRAM Requirements**: ~5.5GB to 8GB
- **Note**: If you are running on an RTX 4060 Ti or higher, ensure Ollama is utilizing the GPU for sub-100ms response times.

### 2. Python Environment
- **Version**: Python 3.10 or 3.11
- **Key Libraries**:
  - `fastapi` & `uvicorn` (For the high-speed local bridge)
  - `re` (For the production-hardened Guillotine Parser)
  - `aiohttp` (For non-blocking communication with Ollama)

### 3. IDE Integration (VS Code)
- **Extension Host**: VS Code 1.85.0+
- **Communication**: SemanticGuard Server defaults to `localhost:8000`. Ensure this port is not blocked by local firewalls.

### 4. Filesystem Structure
Upon initialization, SemanticGuard manages the following in your project root:
- `.semanticguard/semanticguard_vault/` - Holds your cryptographically-signed Architectural Pillar snapshots
- `.semanticguard/Walkthrough.md` - The live Audit Ledger and Reference Architecture
- `.semanticguard/.semanticguard.lock` - SHA-256 signature of the vault (DO NOT EDIT)

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10 or 3.11
- Ollama with llama3.1 model: `ollama pull llama3.1:8b`
- VS Code 1.85.0+

### Installation

1. **Start the SemanticGuard Server**
   ```bash
   cd semanticguard_server
   python -m uvicorn server:app --reload
   ```
   Wait for the "✅ SemanticGuard_Model_V2 ready" message.

2. **Install VS Code Extension**
   - Open VS Code
   - Install the SemanticGuard Gatekeeper extension from the marketplace
   - Or install from source: `cd extension && npm install && code --install-extension .`

3. **Initialize Your Project**
   - The `.semanticguard` folder auto-creates on first server start
   - Edit `.semanticguard/system_rules.md` to define your architectural rules
   - Edit `.semanticguard/golden_state.md` to define your project architecture

4. **Test the Seatbelt**
   - Make a code change in your project
   - Save the file
   - Watch SemanticGuard evaluate it in real-time
   - Status bar shows: `🛡️ SemanticGuard ✅`

---

## 🛠️ The Developer's Audit

When SemanticGuard rejects a change, don't just take its word for it:

1. **Open the Side-by-Side Review**
   - Click the ⚙️ Gear Icon in the SemanticGuard Vault UI
   - Select "Review Changes vs. Walkthrough"

2. **Compare**
   - Code on the Left | Audit Trail on the Right
   - See exactly which Pillar was violated
   - Understand why the "Guillotine" dropped

3. **Verify**
   - Check if the AI's reasoning matches reality
   - Look for hallucinations or context drift
   - Override if the AI is wrong (you're in control)

---

## 📋 The Six Pillars of the SemanticGuard Vault

SemanticGuard enforces architectural consistency and dynamic learning through six core documents in `.semanticguard/`:

1. **`golden_state.md` (The Whitelist):** Your project's mandatory blueprint.
2. **`system_rules.md` (The Blacklist):** The security gatekeeper.
3. **`done_tasks.md`:** A log of successfully completed work.
4. **`pending_tasks.md`:** The actionable TODO list for the AI or developer.
5. **`problems_and_resolutions.md`:** A record of technical roadblocks encountered and their exact solutions.
6. **`history_phases.md`:** The project's evolutionary timeline.

**🔄 The Agentic Feedback Loop:**
If a problem occurs leading to an architectural Pivot:
* The failed approach is added to `system_rules.md` (Blacklist).
* The successful solution is added to `golden_state.md` (Whitelist).

---

## 🏛️ The Cryptographic Vault
SemanticGuard protects your architectural rules with a cryptographic vault in `.semanticguard/semanticguard_vault/`. 
- **Meta-Gate Validation**: Changes to your rules (`.semanticguard/*.md`) are reviewed by a specialized Meta-Gate AI to ensure intent is preserved.
- **SHA-256 Locking**: The entire vault is signed in `.semanticguard.lock` to prevent unauthorized out-of-band tampering.

---

## 🎓 Philosophy
AI should be a skeptical partner, not a yes-man. SemanticGuard optimizes for **architectural integrity**, ensuring your project's soul isn't lost in the "vibe" of rapid AI iteration.

**Your code stays on your machine. Always.**

| `SemanticGuard: Show Server Status` | Check if server is online |
| `SemanticGuard: Toggle Airbag On/Off` | Enable/disable save blocking |
| `SemanticGuard: Open SemanticGuard Ledger` | View Walkthrough.md |
| `SemanticGuard: Review Changes vs. Walkthrough` | Side-by-side code + audit view |
| `Ask SemanticGuard` | Highlight code and ask for evaluation |

---

## ⚙️ Configuration

Edit VS Code settings (`settings.json`):

```json
{
  "semanticguard.serverUrl": "http://127.0.0.1:8000",
  "semanticguard.enabled": true,
  "semanticguard.timeoutMs": 30000,
  "semanticguard.excludePatterns": [
    "**/node_modules/**",
    "**/.git/**",
    "**/*.md",
    "**/*.json"
  ]
}
```

---

## 🐛 Troubleshooting

### Server won't start
- Check Ollama is running: `ollama list`
- Verify llama3.1 is installed: `ollama pull llama3.1:8b`
- Check port 8000 is available
- Ensure Python 3.10 or 3.11 is installed

### Extension not working
- Verify server is running (status bar shows green shield)
- Check server URL in settings matches `http://127.0.0.1:8000`
- Reload VS Code window: Click the ⚙️ Gear Icon → "Reload Window"
- Check firewall isn't blocking localhost:8000

### Saves always blocked
- Check `.semanticguard/system_rules.md` for overly strict rules
- Review `Walkthrough.md` to see why saves are rejected
- Temporarily disable: Click the ⚙️ Gear Icon → "Toggle Airbag On/Off"

### Vault Compromised Error
- This means `.semanticguard/semanticguard_vault/` files or `.semanticguard.lock` were manually edited
- To fix: Review your pillar files, then run the "Re-sign Vault" command from the SemanticGuard sidebar
- Or use the API: `curl -X POST http://127.0.0.1:8000/resign_vault`

### Slow Response Times
- Check GPU utilization: `nvidia-smi` (should show Ollama using GPU)
- Verify quantization: `ollama show llama3.1:8b` (should show Q4_K_M or similar)
- Ensure VRAM isn't exhausted by other processes

---

## 📚 Documentation

- **CLOSED_LOOP_AUDIT_IMPLEMENTATION.md** - Technical implementation details
- **QUICK_START_CLOSED_LOOP.md** - User-friendly quick start guide
- **ARCHITECTURE_DIAGRAM.md** - Visual system architecture
- **Walkthrough.md** - Your live audit trail (auto-generated)

---

## 🎓 Philosophy

SemanticGuard is built on the principle that **AI should be a skeptical partner, not a yes-man**. 

Most AI coding assistants optimize for speed and convenience. SemanticGuard optimizes for **architectural integrity**. It's designed for:

- **Security-conscious developers** who can't afford to leak code to the cloud
- **Solo developers** who need a second pair of eyes on architectural decisions
- **Teams** who want to enforce consistent patterns across the codebase
- **High-stakes environments** where architectural drift has real consequences

---

## 🚨 Beta Status

SemanticGuard is currently in a **14-day Private Beta**. As a solo developer building in a high-stakes environment, I value your technical feedback above all else.

If SemanticGuard catches a drift for you, consider:
- Starring the repo
- Reporting issues on GitHub
- Sharing your use case

---

## 📄 License

[Your License Here]

---

## 🛡️ Built with Integrity

SemanticGuard was built by a developer who needed it. No VC funding. No cloud dependencies. No compromises on privacy.

**Your code stays on your machine. Always.**
"""

    # Only manage .semanticguard/README.md — root README is the developer's responsibility
    if not os.path.exists(readme_path):
        print(f"\n[README GUARDIAN] Initializing SemanticGuard README.md at {readme_path}...")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)
        print(f"[README GUARDIAN] .semanticguard/README.md created successfully.")
    else:
        with open(readme_path, "r", encoding="utf-8") as f:
            if "The Six Pillars" not in f.read():
                print(f"[README GUARDIAN] Upgrading .semanticguard/README.md to 6-Pillar Architecture...")
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(readme_content)
                print(f"[README GUARDIAN] .semanticguard/README.md upgraded.")


def prepend_line_numbers(code: str) -> str:
    """Prepends line numbers to each line of code in the format 'N | code'."""
    lines = code.split('\n')
    numbered_lines = []
    for i, line in enumerate(lines, 1):
        numbered_lines.append(f"{i} | {line}")
    return '\n'.join(numbered_lines)

def parse_violation_details(reasoning: str, system_rules_content: str, code_content: str = "") -> list:
    """
    Parse structured violation details from LLM reasoning text.
    Extracts rule IDs, rule names, locations, and violation descriptions.
    
    Returns a list of dicts with: rule_id, rule_name, rule_location, violation, line_number
    """
    violations = []
    
    # Pattern 1: [source:RULE #N (NAME)] — "code snippet"
    pattern1 = re.finditer(
        r'\[source:(?:RULE\s*#?(\d+)\s*(?:\(([^)]+)\))?|SYSTEM_RULES?)\]\s*[—-]\s*["\']?([^"\'\n]+)["\']?',
        reasoning, re.IGNORECASE
    )
    for m in pattern1:
        rule_num = m.group(1) or ""
        rule_name_raw = m.group(2) or ""
        violation_text = m.group(3).strip() if m.group(3) else ""
        
        # Find rule location in system_rules.md
        rule_location = ""
        if rule_num and system_rules_content:
            lines = system_rules_content.split('\n')
            for i, line in enumerate(lines, 1):
                if f"Rule {rule_num}" in line or f"Rule #{rule_num}" in line:
                    rule_location = f"system_rules.md:L{i}"
                    # Try to get rule name from the line if not already found
                    if not rule_name_raw:
                        name_match = re.search(r'Rule\s*#?\d+[:\s]+([A-Z_]+)', line)
                        if name_match:
                            rule_name_raw = name_match.group(1)
                    break
        
        # Find line number in code where violation occurs
        line_number = 0
        if violation_text and code_content:
            # Extract the actual code from the violation text (strip quotes)
            code_snippet = violation_text.strip('"\'').strip()
            # If the snippet starts with "N | ", try to extract N
            snippet_match = re.match(r'^(\d+)\s*\|\s*(.*)', code_snippet)
            if snippet_match:
                line_number = int(snippet_match.group(1))
                code_snippet = snippet_match.group(2)
            
            code_lines = code_content.split('\n')
            if line_number == 0: # If not found via prefix, try fuzzy match
                for i, line in enumerate(code_lines, 1):
                    if code_snippet and code_snippet[:30] in line:
                        line_number = i
                        break
        
        violations.append({
            "rule_id": f"#{rule_num}" if rule_num else "SYSTEM_RULES",
            "rule_name": rule_name_raw.strip(),
            "rule_location": rule_location,
            "violation": violation_text,
            "line_number": line_number
        })
    
    # Pattern 2: Rule #N: NAME or ## Rule N: NAME in reasoning
    if not violations:
        pattern2 = re.finditer(
            r'(?:Rule\s*#?(\d+)[:\s]+([A-Z_]+)|violates?\s+["\']?([^"\'\n.]+)["\']?)',
            reasoning, re.IGNORECASE
        )
        for m in pattern2:
            rule_num = m.group(1) or ""
            rule_name_raw = m.group(2) or ""
            violation_text = m.group(3) or ""
            
            rule_location = ""
            if rule_num and system_rules_content:
                lines = system_rules_content.split('\n')
                for i, line in enumerate(lines, 1):
                    if f"Rule {rule_num}" in line or f"Rule #{rule_num}" in line:
                        rule_location = f"system_rules.md:L{i}"
                        break
            
            if rule_num or violation_text:
                violations.append({
                    "rule_id": f"#{rule_num}" if rule_num else "",
                    "rule_name": rule_name_raw.strip(),
                    "rule_location": rule_location,
                    "violation": violation_text.strip(),
                    "line_number": 0
                })
    
    # Deduplicate by rule_id + violation
    seen = set()
    unique = []
    for v in violations:
        key = (v["rule_id"], v["violation"][:40])
        if key not in seen:
            seen.add(key)
            unique.append(v)
    
    return unique[:5]  # Cap at 5 violations to keep sidebar clean


def append_audit_ledger(action: str, reasoning: str):
    """
    Appends the parsed LLM execution thought process to Walkthrough.md.
    """
    try:
        root_dir = get_root_dir()
        semanticguard_dir = os.path.join(root_dir, ".semanticguard")
        ledger_path = find_walkthrough_file(semanticguard_dir)
        
        # Ensure file exists
        if not os.path.exists(ledger_path):
            logger.warning(f"Walkthrough.md not found at {ledger_path}, creating it...")
            initialize_audit_ledger(semanticguard_dir)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"\n## {timestamp} | Result: {action}\n"
            f"**Thought Process:**\n"
            f"> {reasoning.strip()}\n"
        )
        
        with open(ledger_path, "a", encoding="utf-8") as f:
            f.write(entry)
        
        logger.info(f"✅ Appended to Walkthrough.md: {action} ({len(reasoning)} chars)")
        
    except Exception as e:
        logger.error(f"❌ Failed to append to Walkthrough.md: {e}")
        logger.error(f"   Path: {ledger_path if 'ledger_path' in locals() else 'unknown'}")
        logger.error(f"   Root dir: {root_dir if 'root_dir' in locals() else 'unknown'}")

def verify_ai_walkthrough(ai_generated_explanation: str, golden_rules_path: str):
    """
    Takes the AI's explanation of what it did and compares it 
    against the ground truth rules in the vault.
    """
    if os.path.exists(golden_rules_path):
        with open(golden_rules_path, 'r', encoding="utf-8") as f:
            rules = f.read()
    else:
        rules = "NO SYSTEM RULES FOUND."

    # The Prompt for the 8B Model to act as the "Auditor"
    audit_prompt = f"""SYSTEM: You are the SEMANTICGUARD ARCHITECT. 
Your job is to compare an AI's EXPLANATION of its work against the PROJECT RULES.

PROJECT RULES:
{rules}

AI EXPLANATION OF WORK:
{ai_generated_explanation}

TASK: Did the AI's intent violate any rules? 
Output [ACTION] ACCEPT if the intent is valid.
Output [ACTION] REJECT if the intent violates a rule.

[THOUGHT]"""
    
    raw = generate(audit_prompt)
    
    print("\n" + "="*40)
    print("🕵️ SEMANTICGUARD VALIDATION ENGINE THOUGHTS:")
    print(raw)
    print("="*40 + "\n")
    
    return guillotine_parser(raw)

def verify_against_ledger(current_reasoning: str) -> dict:
    """
    Closed-Loop Audit: Compares the current AI reasoning against the Reference Architecture
    in the Walkthrough.md ledger to detect hallucinations and context drift.
    
    Reads the first 50 lines (the ground truth) from Walkthrough.md and uses the LLM
    to verify if the current reasoning contradicts the established baseline.
    
    Returns:
        dict with keys: verdict (ACCEPT/REJECT), score (0.0-1.0), reasoning (explanation)
    """
    root_dir = get_root_dir()
    semanticguard_dir = os.path.join(root_dir, ".semanticguard")
    ledger_path = find_walkthrough_file(semanticguard_dir)
    
    if not os.path.exists(ledger_path):
        logger.warning("Walkthrough ledger not found — skipping closed-loop audit")
        return {
            "verdict": "ACCEPT",
            "score": 0.0,
            "reasoning": "Ledger not initialized yet — first run bypass"
        }
    
    # Read the Reference Architecture (first 50 lines = ground truth)
    with open(ledger_path, 'r', encoding="utf-8") as f:
        lines = f.readlines()
        reference_architecture = "".join(lines[:50])
    
    # The Closed-Loop Audit Prompt
    audit_prompt = f"""SYSTEM: You are the SEMANTICGUARD AUDITOR.
Your job is to compare the CURRENT AI REASONING against the REFERENCE ARCHITECTURE baseline.

REFERENCE ARCHITECTURE (The Ground Truth):
{reference_architecture}

CURRENT AI REASONING:
{current_reasoning}

TASK: Does the current reasoning contradict or deviate from the Reference Architecture?
- Check for hallucinations (making up facts not in the reference)
- Check for rule violations (ignoring principles from the reference)
- Check for architectural drift (introducing patterns that contradict the baseline)

Output [ACTION] ACCEPT if the reasoning aligns with the reference.
Output [ACTION] REJECT if the reasoning contradicts the reference or shows drift.

[THOUGHT]"""
    
    raw = generate(audit_prompt)
    
    print("\n" + "="*40)
    print("🔍 SEMANTICGUARD CLOSED-LOOP AUDIT:")
    print(raw)
    print("="*40 + "\n")
    
    result = guillotine_parser(raw)
    
    if result['verdict'] == "REJECT":
        logger.warning(f"Closed-loop audit detected drift: {result['reasoning'][:100]}")
    
    return result

def initialize_project_with_template(mode: str, project_path: str, processor_mode: str = "gpu") -> dict:
    """
    Initializes a SemanticGuard project with a golden template.
    
    Steps:
    1. Create .semanticguard directory structure
    2. Write system_rules.md based on chosen mode
    3. Generate golden_state.md using LLM
    3. Initialize other pillar files
    4. Initialize Walkthrough.md and README.md
    5. Generate golden_state.md using LLM
    6. Create vault snapshots and lock
    
    Returns:
        dict with status and message
    """
    if mode not in GOLDEN_TEMPLATES:
        return {"status": "error", "message": f"Invalid mode: {mode}. Must be one of: {', '.join(GOLDEN_TEMPLATES.keys())}"}
    
    template = GOLDEN_TEMPLATES[mode]
    semanticguard_dir = os.path.join(project_path, ".semanticguard")
    
    try:
        # Step 1: Create directory structure
        os.makedirs(semanticguard_dir, exist_ok=True)
        vault_dir = os.path.join(semanticguard_dir, "semanticguard_vault")
        os.makedirs(vault_dir, exist_ok=True)
        
        print(f"\n[GOLDEN TEMPLATE] Initializing project with mode: {template['name']}")
        
        # Step 2: Write system_rules.md
        rules_path = os.path.join(semanticguard_dir, "system_rules.md")
        with open(rules_path, "w", encoding="utf-8") as f:
            f.write(template['system_rules'])
        print(f"[GOLDEN TEMPLATE] Created system_rules.md for {mode} mode")
        
        # Step 3: Initialize other pillar files (MOVED UP before LLM call)
        pillars_to_create = {
            "done_tasks.md": "# Completed Tasks\n\nNo tasks completed yet.\n",
            "pending_tasks.md": "# Pending Tasks\n\nNo pending tasks.\n",
            "history_phases.md": f"# Project History\n\n## Phase 1: Initialization\n- Project initialized with {template['name']} mode\n- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            "problems_and_resolutions.md": "# Problems and Resolutions\n\nNo problems reported yet.\n"
        }
        
        for filename, content in pillars_to_create.items():
            pillar_path = os.path.join(semanticguard_dir, filename)
            if not os.path.exists(pillar_path): # Prevent overwriting if file exists
                with open(pillar_path, "w", encoding="utf-8") as f:
                    f.write(content)
        
        print(f"[GOLDEN TEMPLATE] Created all pillar files")

        # Step 4: Initialize Walkthrough.md and README.md
        initialize_audit_ledger(semanticguard_dir)
        initialize_project_readme(project_path)
        
        # Step 5: Generate golden_state.md using LLM (STAY ROBUST)
        print(f"[GOLDEN TEMPLATE] Generating Perfect Execution example using Llama 3.1 8B...")
        
        golden_example = ""
        try:
            golden_prompt = template['llm_prompt']
            # Pass processor_mode to generate()
            golden_example = generate(golden_prompt, processor_mode=processor_mode)
        except Exception as llm_err:
            logger.warning(f"LLM generation failed for golden_state.md: {llm_err}")
            golden_example = f"\n> [!WARNING]\n> **LLM OFFLINE/BUSY:** Perfect Execution example generation failed.\n> SemanticGuard will learn from your first few accepted code changes instead.\n\n_Reason: {str(llm_err)}_"

        golden_state_content = f"""# Golden State - {template['name']}

## Mode Description
{template['description']}

## Perfect Execution Example

{golden_example}

## Architectural Principles

This project follows the **{mode}** architectural style. All code changes must align with the rules defined in `system_rules.md` and follow the patterns demonstrated in the Perfect Execution example above.

### Key Principles:
"""
        
        # Add mode-specific principles
        if mode == "solo-indie":
            golden_state_content += """
- Keep functions under 50 lines
- Maximum 3 levels of nesting
- Clear, descriptive naming
- Comment the 'why', not the 'what'
- DRY principle - no code duplication
"""
        elif mode == "clean-layers":
            golden_state_content += """
- Strict layer separation (Presentation, Business Logic, Data Access)
- Dependency direction: outer depends on inner
- Interface contracts at layer boundaries
- Single Responsibility Principle
- Dependency Injection
"""
        elif mode == "secure-stateless":
            golden_state_content += """
- Zero Trust Architecture - validate everything
- Stateless sessions with JWT tokens
- Input sanitization is mandatory
- Encryption everywhere (TLS 1.3+, AES-256)
- Audit logging for all security events
- Privacy by design
"""
        
        golden_state_path = os.path.join(semanticguard_dir, "golden_state.md")
        with open(golden_state_path, "w", encoding="utf-8") as f:
            f.write(golden_state_content)
        print(f"[GOLDEN TEMPLATE] Created golden_state.md")
        
        # Step 6: Create vault snapshots and lock
        for pillar in PILLARS:
            src = os.path.join(semanticguard_dir, pillar)
            dst = os.path.join(vault_dir, pillar)
            if os.path.exists(src):
                shutil.copy2(src, dst)
        
        write_vault_lock(project_path)
        print(f"[GOLDEN TEMPLATE] Vault initialized and cryptographically signed")
        
        return {
            "status": "success",
            "message": f"Project initialized with {template['name']} mode",
            "mode": mode,
            "template_name": template['name']
        }
        
    except Exception as e:
        logger.error(f"Failed to initialize project: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"Initialization failed: {str(e)}"
        }

def move_task_to_done(task_description: str, project_path: str, problems_encountered: str = "") -> dict:
    """
    Moves a completed task from pending_tasks.md to done_tasks.md.
    EVOLUTIONARY LOGIC: Automatically updates history_phases.md with completion summary.
    
    Args:
        task_description: The task text to move
        project_path: Absolute path to project root
        problems_encountered: Optional description of problems faced during this task
        
    Returns:
        dict with status and message
    """
    semanticguard_dir = os.path.join(project_path, ".semanticguard")
    pending_path = os.path.join(semanticguard_dir, "pending_tasks.md")
    done_path = os.path.join(semanticguard_dir, "done_tasks.md")
    history_path = os.path.join(semanticguard_dir, "history_phases.md")
    
    try:
        # Read pending tasks
        if not os.path.exists(pending_path):
            return {"status": "error", "message": "pending_tasks.md not found"}
        
        with open(pending_path, "r", encoding="utf-8") as f:
            pending_content = f.read()
        
        # Check if task exists in pending
        if task_description not in pending_content:
            return {"status": "error", "message": f"Task not found in pending_tasks.md: {task_description}"}
        
        # Remove from pending
        lines = pending_content.split('\n')
        new_pending_lines = [line for line in lines if task_description not in line]
        new_pending_content = '\n'.join(new_pending_lines)
        
        # Add to done with timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        done_entry = f"\n## {timestamp}\n- {task_description}\n"
        
        if os.path.exists(done_path):
            with open(done_path, "a", encoding="utf-8") as f:
                f.write(done_entry)
        else:
            with open(done_path, "w", encoding="utf-8") as f:
                f.write(f"# Completed Tasks\n{done_entry}")
        
        # Write updated pending
        with open(pending_path, "w", encoding="utf-8") as f:
            f.write(new_pending_content)
        
        # EVOLUTIONARY LOGIC GATE 3: Update history_phases.md with completion
        history_entry = f"\n## Task Completion: {timestamp}\n"
        history_entry += f"**Completed**: {task_description}\n"
        if problems_encountered:
            history_entry += f"**Problems Encountered**: {problems_encountered}\n"
            history_entry += f"**Reference**: See problems_and_resolutions.md for detailed context\n"
        else:
            history_entry += f"**Status**: Completed without major issues\n"
        history_entry += "\n"
        
        if os.path.exists(history_path):
            with open(history_path, "a", encoding="utf-8") as f:
                f.write(history_entry)
        else:
            with open(history_path, "w", encoding="utf-8") as f:
                f.write(f"# Project History\n{history_entry}")
        
        print(f"[EVOLUTIONARY GATE 3] ✅ Updated history_phases.md with task completion")
        
        # Update vault
        vault_dir = os.path.join(semanticguard_dir, "semanticguard_vault")
        for filename in ["pending_tasks.md", "done_tasks.md", "history_phases.md"]:
            src = os.path.join(semanticguard_dir, filename)
            dst = os.path.join(vault_dir, filename)
            if os.path.exists(src):
                shutil.copy2(src, dst)
        
        write_vault_lock(project_path)
        
        logger.info(f"Task moved to done: {task_description}")
        return {"status": "success", "message": f"Task completed and history updated: {task_description}"}
        
    except Exception as e:
        logger.error(f"Failed to move task: {e}")
        return {"status": "error", "message": str(e)}

def evolve_architectural_memory(project_path: str) -> dict:
    """
    The Memory-to-Law Pipeline with Evolutionary Logic Gates.
    
    AUTOMATIC PROCESSING:
    1. Scans problems_and_resolutions.md for patterns
    2. RESOLVED problems → Success Patterns → golden_state.md
    3. UNRESOLVED problems → Negative Rules → system_rules.md
    4. Updates history_phases.md with lessons learned
    5. Syncs all changes to vault and re-signs
    
    This implements the full evolutionary feedback loop without manual intervention.
    
    Args:
        project_path: Absolute path to project root
        
    Returns:
        dict with status, patterns_added, rules_added, history_updated
    """
    semanticguard_dir = os.path.join(project_path, ".semanticguard")
    problems_path = os.path.join(semanticguard_dir, "problems_and_resolutions.md")
    golden_path = os.path.join(semanticguard_dir, "golden_state.md")
    rules_path = os.path.join(semanticguard_dir, "system_rules.md")
    history_path = os.path.join(semanticguard_dir, "history_phases.md")
    
    try:
        if not os.path.exists(problems_path):
            return {"status": "error", "message": "problems_and_resolutions.md not found"}
        
        with open(problems_path, "r", encoding="utf-8") as f:
            problems_content = f.read()
        
        # EVOLUTIONARY LOGIC GATE: Analyze problems with prioritization hierarchy
        analysis_prompt = f"""SYSTEM: You are the SEMANTICGUARD EVOLUTIONARY ANALYZER.
Your job is to extract architectural lessons and apply the Pillar Prioritization Hierarchy.

PILLAR PRIORITIZATION HIERARCHY:
1. system_rules.md = THE LAW (Highest Priority) - Violations must generate negative rules
2. golden_state.md = THE VISION - Success patterns become the new standard
3. problems_and_resolutions.md = THE MEMORY - Prevents repeating failures

PROBLEMS AND RESOLUTIONS:
{problems_content}

EVOLUTIONARY LOGIC GATES:

GATE 1: PROBLEM DETECTION & ROUTING
────────────────────────────────────
Analyze each problem and classify:
- RESOLVED: Solution worked → Extract success pattern for golden_state.md
- UNRESOLVED: User gave up or pivoted → Extract negative rule for system_rules.md
- RECURRING: Same problem appears multiple times → URGENT negative rule needed

GATE 2: PATTERN EXTRACTION
───────────────────────────
For RESOLVED problems:
- What approach worked?
- Why did it work?
- How can this become a reusable pattern?
Format: "Pattern: Use X for Y because Z"

GATE 3: NEGATIVE RULE GENERATION
─────────────────────────────────
For UNRESOLVED/RECURRING problems:
- What was attempted?
- Why did it fail?
- What should be forbidden?
Format: "NEVER use X because it causes Y in context Z"

OUTPUT FORMAT (MANDATORY):
[RESOLVED_PATTERNS]
- Pattern 1: [Detailed success pattern with context]
- Pattern 2: [Another pattern]
(or "NONE" if no resolved problems)

[NEGATIVE_RULES]
- Rule 1: NEVER [specific action] because [specific failure reason]
- Rule 2: NEVER [another action] because [another reason]
(or "NONE" if no unresolved problems)

[LESSONS_LEARNED]
- Lesson 1: [High-level takeaway for history_phases.md]
- Lesson 2: [Another lesson]
(or "NONE" if no lessons)

Begin analysis:
[RESOLVED_PATTERNS]"""
        
        # Native PyTorch integration - using generate
        analysis = generate(analysis_prompt)
        
        print("\n" + "="*60)
        print("🧠 SEMANTICGUARD EVOLUTIONARY MEMORY ANALYSIS:")
        print("="*60)
        print(analysis)
        print("="*60 + "\n")
        
        # Parse the analysis
        patterns_added = 0
        rules_added = 0
        lessons_added = 0
        
        # Extract sections
        sections = {}
        if "[RESOLVED_PATTERNS]" in analysis:
            sections['patterns'] = analysis.split("[RESOLVED_PATTERNS]")[1].split("[NEGATIVE_RULES]")[0].strip() if "[NEGATIVE_RULES]" in analysis else ""
        if "[NEGATIVE_RULES]" in analysis:
            sections['rules'] = analysis.split("[NEGATIVE_RULES]")[1].split("[LESSONS_LEARNED]")[0].strip() if "[LESSONS_LEARNED]" in analysis else analysis.split("[NEGATIVE_RULES]")[1].strip()
        if "[LESSONS_LEARNED]" in analysis:
            sections['lessons'] = analysis.split("[LESSONS_LEARNED]")[1].strip()
        
        # GATE 1: Add success patterns to golden_state.md
        if sections.get('patterns') and "NONE" not in sections['patterns'].upper():
            with open(golden_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n## 🌟 Evolved Patterns (Learned from Experience)\n")
                f.write(f"_Auto-generated by Evolutionary Logic Gate on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n\n")
                f.write(sections['patterns'])
                f.write("\n")
            patterns_added = len([line for line in sections['patterns'].split('\n') if line.strip().startswith('-')])
            print(f"[EVOLUTIONARY GATE 1] ✅ Added {patterns_added} success patterns to golden_state.md")
        
        # GATE 2: Add negative rules to system_rules.md
        if sections.get('rules') and "NONE" not in sections['rules'].upper():
            with open(rules_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n## 🚫 Evolved Rules (Learned from Failures)\n")
                f.write(f"_Auto-generated by Evolutionary Logic Gate on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n\n")
                f.write(sections['rules'])
                f.write("\n")
            rules_added = len([line for line in sections['rules'].split('\n') if line.strip().startswith('-')])
            print(f"[EVOLUTIONARY GATE 2] ✅ Added {rules_added} negative rules to system_rules.md")
        
        # GATE 3: Add lessons to history_phases.md
        if sections.get('lessons') and "NONE" not in sections['lessons'].upper():
            with open(history_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n## 📚 Lessons Learned from Memory Evolution\n")
                f.write(f"_Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n\n")
                f.write(sections['lessons'])
                f.write("\n\n**Related Problems**: See problems_and_resolutions.md for detailed context\n")
            lessons_added = len([line for line in sections['lessons'].split('\n') if line.strip().startswith('-')])
            print(f"[EVOLUTIONARY GATE 3] ✅ Added {lessons_added} lessons to history_phases.md")
        
        # GATE 4: Sync to vault and re-sign
        vault_dir = os.path.join(semanticguard_dir, "semanticguard_vault")
        for filename in ["golden_state.md", "system_rules.md", "history_phases.md"]:
            src = os.path.join(semanticguard_dir, filename)
            dst = os.path.join(vault_dir, filename)
            if os.path.exists(src):
                shutil.copy2(src, dst)
        
        write_vault_lock(project_path)
        print(f"[EVOLUTIONARY GATE 4] ✅ Vault synced and cryptographically signed")
        
        return {
            "status": "success",
            "patterns_added": patterns_added,
            "rules_added": rules_added,
            "lessons_added": lessons_added,
            "message": f"Memory evolved: {patterns_added} patterns, {rules_added} rules, {lessons_added} lessons"
        }
        
    except Exception as e:
        logger.error(f"Failed to evolve memory: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

# (Ollama integration completely removed in favor of native PyTorch/Unsloth inference)
_model_ready = False

# ─── Global Cloud Rate Limiter ──────────────────────────────────────────────
# Instantiate a global TokenBucket for cloud API rate limiting
# Default: 30 RPM, 30,000 TPM (Groq free tier)
# Will be upgraded when UI sends detected limits via /update_rate_limits endpoint
cloud_rate_limiter = TokenBucket(max_rpm=30, max_tpm=30000)
logger.info("🌩️ Cloud rate limiter initialized: 30 RPM, 30,000 TPM")

# ─── Outbound HTTP Semaphore (Thundering Herd Prevention) ──────────────────
# Limits simultaneous socket connections to Groq API
# Even if 10 requests wake from sleep simultaneously, only 3 can call Groq at once
groq_outbound_semaphore = asyncio.Semaphore(3)
logger.info("🚦 Groq outbound semaphore initialized: max 3 concurrent HTTP connections")
global_eval_semaphore = asyncio.Semaphore(2)
logger.info("🚦 Global evaluation semaphore initialized: max 2 concurrent evaluations")

# ─── Golden System Prompt (98% Accuracy from stress_test.py) ───────────────




@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load the model during server startup with comprehensive error handling."""
    global _model_ready
    logger.info("🔄 Starting SemanticGuard Gatekeeper server…")
    
    # ── GPU Contention Prevention ─────────────────────────────────────────
    # Set Ollama optimization flags before any inference calls.
    # OLLAMA_NUM_PARALLEL=1 dedicates 100% GPU to one request at a time.
    # This eliminates CUDA scheduling overhead between concurrent contexts.
    import os as _os
    _os.environ.setdefault("OLLAMA_NUM_PARALLEL", "1")
    _os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
    _os.environ.setdefault("OLLAMA_GPU_OVERHEAD", "0")
    logger.info("🎮 GPU optimization flags set: OLLAMA_NUM_PARALLEL=1, CUDA_VISIBLE_DEVICES=0")
    
    # EMERGENCY FIX 1: Wrap init_vault in try/except with full traceback
    try:
        # Action 3: Wire startup initialization
        sink_registry.load()
        logger.info("🛡️ Sink registry initialized. Active sinks: %s", 
                    sink_registry._current_registry["middleware"])
        init_vault()
        logger.info("✅ Vault initialized successfully")
    except Exception as vault_error:
        logger.error(f"❌ CRITICAL: Vault initialization failed: {vault_error}")
        import traceback
        logger.error("Full traceback:")
        logger.error(traceback.format_exc())
        logger.warning("⚠️  Server will start but vault operations may fail")
    
    # INITIALIZE NATIVE INFERENCE ENGINE: Load SemanticGuard_Model_V2 into VRAM
    try:
        logger.info(f"🔍 Loading Native SemanticGuard Model into VRAM...")
        get_model()  # Loads model and tokenizer into global memory inside model_loader.py
        _model_ready = True
        logger.info("✅ Native PyTorch/Transformers model loaded successfully")
        logger.info("✅ Server accepting requests using local GPU inference")
    except Exception as e:
        logger.error(f"❌ Native model load failed: {e}")
        import traceback
        logger.error("Full traceback:")
        logger.error(traceback.format_exc())
        logger.warning("⚠️  Server will start but /evaluate will return 503 until model is ready")
    
    logger.info("✅ Server startup complete - ready to accept requests")
    yield
    logger.info("🛑 SemanticGuard server shutting down")


# ─── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SemanticGuard Gatekeeper",
    description="Local drift-detection gatekeeper for AI-assisted coding prompts.",
    version="2.0.0",
    lifespan=lifespan,
)

# Allow Antigravity IDE extension (browser) to call us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # localhost extension — safe in local-only context
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── Schemas ────────────────────────────────────────────────────────────────

class EvaluatePillars(BaseModel):
    golden_state:             str = Field("", description="Contents of .semanticguard/golden_state.md")
    done_tasks:               str = Field("", description="Contents of .semanticguard/done_tasks.md")
    pending_tasks:            str = Field("", description="Contents of .semanticguard/pending_tasks.md")
    history_phases:           str = Field("", description="Phase history (optional)")
    system_rules:             str = Field("", description="Contents of .semanticguard/system_rules.md")
    problems_and_resolutions: str = Field("", description="Contents of .semanticguard/problems_and_resolutions.md (optional)")

class EvaluateRequest(BaseModel):
    filename:       str = Field(..., description="Filename being saved")
    code_snippet:   str = Field(..., description="Content of the file")
    pillars:        EvaluatePillars = Field(default_factory=EvaluatePillars)
    project_path:   str = Field("",    description="Absolute path to the project root")
    processor_mode: Optional[str] = Field("gpu", description="CPU or GPU usage for inference")
    model_name:     str = Field("deepseek-r1:7b", description="Model to use for inference")
    power_mode:     bool = Field(False, description="If True, run Layer 1 only and skip Layer 2 (for cloud routing)")

class EvaluatePillarRequest(BaseModel):
    filename:         str = Field(..., description="The name of the pillar, e.g. system_rules.md")
    incoming_content: str = Field(..., description="The content of the pillar that the user is trying to save")
    project_path:     str = Field("",  description="Optional: Absolute path to the project root (sent by extension)")
    processor_mode:   Optional[str] = Field("GPU", description="CPU or GPU usage for inference")
    model_name:       str = Field("deepseek-r1:7b", description="Model to use for inference")

class VerifyIntentRequest(BaseModel):
    ai_explanation: str = Field(..., description="The AI's generated walkthrough/explanation of its work.")

class InitializeProjectRequest(BaseModel):
    mode:           str = Field(..., description="The golden template mode: solo-indie, clean-layers, or secure-stateless")
    project_path:   str = Field(..., description="Absolute path to the project root directory")
    processor_mode: Optional[str] = Field("gpu", description="CPU or GPU usage for inference")

class ResignResponse(BaseModel):
    status: str
    message: str

class ViolationDetail(BaseModel):
    rule_id:       str = Field("", description="Rule identifier e.g. Rule #100")
    rule_name:     str = Field("", description="Rule name e.g. DOM_INTEGRITY_PROTECTION")
    rule_location: str = Field("", description="Where rule is defined e.g. system_rules.md:L156")
    violation:     str = Field("", description="What was violated e.g. innerHTML usage")
    line_number:   int = Field(0,  description="Line number in the file where violation occurs")
    suggested_fix: str = Field("", description="AI-suggested code replacement")
    data_flow:     str = Field("", description="Data flow trace (Source -> Sink)")
    sensitive_var: str = Field("", description="Sensitive variable identified")
    trigger_type:  str = Field("", description="VARIABLE or STRING trigger")
    confidence:    str = Field("", description="HIGH or LOW confidence")

class EvaluateResponse(BaseModel):
    action:        str   = Field(...,  description="ACCEPT, REJECT, or ERROR")
    drift_score:   float = Field(...,  description="0.0 (clean) – 1.0 (high drift)")
    reasoning:     str   = Field(...,  description="Cleaned [THOUGHT] reasoning text")
    vault_updated: bool  = Field(False, description="True if the vault snapshot was updated")
    vault_file:    str   = Field("",    description="Which vault file was updated (on ACCEPT)")
    # Structured violation details for sidebar display
    filename:      str   = Field("",    description="File that was audited")
    violations:    List[ViolationDetail] = Field(default_factory=list, description="Parsed violation details")
    raw_output:    str   = Field("",    description="Raw LLM output for diagnostics")
    layer:         str   = Field("",    description="Which layer caught it: layer1 (regex) or layer2 (LLM)")


class HealthResponse(BaseModel):
    status:       str  = "ok"
    model_loaded: bool = False
    version:      str  = "2.0.0"
    engine_mode:  str  = "local"  # "local" or "power"


# ─── Routes ─────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Status"])
async def health(request: Request):
    """Quick liveness + readiness check for the IDE extension with rate-limited logging."""
    # Get engine mode from environment variable
    engine_mode = os.environ.get("SEMANTICGUARD_ENGINE_MODE", "local")
    
    # Rate limit health check logs to once per minute
    global _last_health_log_time
    current_time = time.time()
    
    should_log = False
    if not hasattr(health, '_last_log_time'):
        health._last_log_time = 0
    
    if current_time - health._last_log_time >= 60:
        should_log = True
        health._last_log_time = current_time
    
    if should_log:
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        print(f"HEALTH CHECK REQUEST:")
        print(f"   Client IP: {client_ip}")
        print(f"   User-Agent: {user_agent}")
        print(f"   Model Ready: {_model_ready}")
        print(f"   Engine Mode: {engine_mode}")
        print(f"   Timestamp: {datetime.now().isoformat()}")
        
        logger.info(f"Health check from {client_ip} - Model ready: {_model_ready}, Engine: {engine_mode}")
        
        response = HealthResponse(status="ok", model_loaded=_model_ready, engine_mode=engine_mode)
        print(f"   Response: {response.dict()}")
        print("=" * 50)
    
    return HealthResponse(status="ok", model_loaded=_model_ready, engine_mode=engine_mode)


@app.post("/evaluate", response_model=EvaluateResponse, tags=["Gatekeeper"])
async def evaluate(req: EvaluateRequest, request: Request):
    """
    Evaluate a user prompt against the 5 workspace pillars.

    Returns ACCEPT (drift_score < 0.40) or REJECT (drift_score >= 0.40).
    
    If power_mode=True, runs Layer 1 only and returns L1_PASS if clean.
    """
    # Extract API key from Authorization header for Power Mode
    api_key = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]  # Remove "Bearer " prefix
        logger.debug(f"Extracted API key from Authorization header (length: {len(api_key)})")
    
    # ── LOG SIGNAL ──
    # Extra diagnostic log as requested by user
    # cmd_preview = req.code_snippet[:100].replace('\n', ' ')
    # print(f"\n--- AUDIT REQUEST RECEIVED: {req.filename} ({cmd_preview}) ---")

    # HARDWARE CHECK: Log GPU status but never block the audit
    gpu_ok, gpu_msg = verify_gpu_loading()
    if not gpu_ok:
        logger.warning(f"GPU check: {gpu_msg} — continuing audit anyway")
    else:
        logger.info(f"GPU check: {gpu_msg}")

    # RETIRED: keyword_audit_shortcut
    # (Excision of legacy Zero-Baseline logic to enforce structural analysis)
        
    if not _model_ready and not req.power_mode:
        raise HTTPException(
            status_code=503,
            detail="SemanticGuard model is still loading. Retry in a few seconds."
        )

    root_dir = get_root_dir()
    


    # Determine file extension from filename
    file_extension = os.path.splitext(req.filename)[1]
    
    # ── PIPELINE PIPING ──
    # Task 4: build_prompt call with system_rules=""
    # Apply Silent Exclusions (Engineering Way) first
    cleaned_code = clean_code_snippet(req.filename, req.code_snippet)
    if len(cleaned_code) < len(req.code_snippet):
        logger.info(f"🛡️ Silent Exclusion: Stripped internal keys from {req.filename}")

    # GROUNDING: Prepend line numbers to the code snippet
    grounded_code = prepend_line_numbers(cleaned_code)
    
    # ── V2.0 LAYER 1: Risk Surface Detection Screener ──────────────────────
    from semanticguard_server.engine import layer1_screen
    
    layer1_result = layer1_screen(cleaned_code, file_extension, req.filename)
    if layer1_result.verdict == "REJECT":
        from semanticguard_server.engine import layer3_aggregate
        aggregated = layer3_aggregate(layer1_result=layer1_result)
        logger.info(f"Layer 1 caught {len(layer1_result.violations)} violation(s) — skipping model inference")
        append_audit_ledger("REJECT", aggregated.reasoning)
        return EvaluateResponse(
            action="REJECT",
            drift_score=aggregated.drift_score,
            reasoning=aggregated.reasoning,
            violations=aggregated.violations,
            filename=req.filename,
            raw_output=aggregated.raw_output,
            layer="layer1"  # Track which layer caught it
        )
    
    # ── POWER MODE BYPASS: Layer 1 passed, skip Layer 2 ───────────────────
    if req.power_mode:
        logger.info("Power Mode: Layer 1 passed — returning L1_PASS (cloud will handle Layer 2)")
        return EvaluateResponse(
            action="L1_PASS",
            drift_score=0.0,
            reasoning="Layer 1 passed. Cloud routing enabled.",
            violations=[],
            filename=req.filename,
            raw_output="[Layer 1] ACCEPT — No deterministic violations found."
        )
    # ── End Layer 1 ────────────────────────────────────────────────────────
    
    # ── V2.0 LAYER 2: Focused Model Analyzer ───────────────────────────────
    from semanticguard_server.engine import layer2_analyze
    
    # Build the spec for Layer 2 — same spec the v1.0 pipeline used
    spec = extract_data_flow_spec(cleaned_code, file_extension=file_extension)
    sinks_list = ", ".join(sink_registry._current_registry["middleware"])
    
    layer2_result = None
    if spec.get("pii_sources"):
        logger.info(f"Layer 2 analyzing {len(spec['pii_sources'])} PII source(s) — {[s['variable'] for s in spec['pii_sources']]}")
        
        layer2_result = layer2_analyze(
            spec=spec,
            source_code=cleaned_code,
            model_name=req.model_name,
            registered_sinks=sinks_list
        )
        
        if layer2_result.verdict == "REJECT":
            from semanticguard_server.engine import layer3_aggregate
            aggregated = layer3_aggregate(
                layer1_result=layer1_result,
                layer2_result=layer2_result
            )
            append_audit_ledger("REJECT", aggregated.reasoning)
            return EvaluateResponse(
                action="REJECT",
                drift_score=aggregated.drift_score,
                reasoning=aggregated.reasoning,
                violations=aggregated.violations,
                filename=req.filename,
                raw_output=aggregated.raw_output,
                layer="layer2"  # Track which layer caught it
            )
        else:
            logger.info(f"Layer 2 ACCEPT — {layer2_result.details}")
    else:
        logger.info("Layer 2: No PII sources detected by AST extractor — passing to v1.0 pipeline")
    # ── End Layer 2 ────────────────────────────────────────────────────────
    
    prompt = build_prompt(
        system_rules=req.pillars.system_rules,  # Use BYOK rules from extension
        user_command=grounded_code,
        file_extension=file_extension,
        model_name=req.model_name
    )

    # Run inference natively — offloaded to thread pool so the async event loop
    # is NOT blocked during GPU inference. Without this, health checks queue up
    # and the VS Code client disconnects before inference finishes (silent fail).
    # STRUCTURAL_INTEGRITY_SYSTEM is passed as the system prompt so it occupies
    # the Llama 3 <|system|> role instead of eating user token budget.
    t0 = time.perf_counter()
    
    # RETIRED: keyword_audit_shortcut
    # (Excision of legacy prompt overwrite logic)
    
    try:
        # Choose system prompt based on model
        system_prompt = STRUCTURAL_INTEGRITY_SYSTEM_LLAMA if "llama" in req.model_name.lower() else STRUCTURAL_INTEGRITY_SYSTEM
        
        # Pass processor_mode, model_name, engine_mode, and api_key to generate()
        engine_mode = os.environ.get("SEMANTICGUARD_ENGINE_MODE", "local")
        raw = await asyncio.to_thread(generate, prompt, system_prompt, processor_mode=req.processor_mode, model_name=req.model_name, engine_mode=engine_mode, api_key=api_key)

        print("\n" + "="*40)
        print(f"🧠 SEMANTICGUARD RAW THOUGHTS [{req.model_name}]:")
        print(raw)
        print("="*40 + "\n")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Inference error: {error_msg}")
        
        # ── ROBUST ERROR HANDLING: Ollama Connection Error (WinError 10061) ──
        if "10061" in error_msg or "Connection refused" in error_msg or "unreachable" in error_msg:
             return EvaluateResponse(
                action="ERROR",
                drift_score=1.0,
                reasoning="Ollama service is down. Please start Ollama to perform security audit.",
                violations=[],
                filename=req.filename
            )
            
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")

    elapsed = time.perf_counter() - t0
    logger.info(f"Inference took {elapsed:.2f}s — file: {req.filename}")
    print(f"\n⏱️ AUDIT TIME (evaluate): {elapsed:.2f}s\n")

    # Parse result
    # Task 3: Wire guillotine_parser into the response path
    result = guillotine_parser(
        raw_output=raw,
        user_command=cleaned_code
    )
    
    # ── LINE VALIDATION (Anti-Hallucination) ──
    # Discard violations pointing to non-existent lines.
    actual_line_count = len(req.code_snippet.splitlines())
    valid_violations = []
    for v in result['violations']:
        ln = v.get('line_number', 0)
        if 1 <= ln <= actual_line_count:
            valid_violations.append(v)
        else:
            logger.warning(f"🚫 Removing hallucinated violation on non-existent line {ln} (File has {actual_line_count} lines)")
    
    result['violations'] = valid_violations

    # Append execution to Walkthrough ledger
    append_audit_ledger(result['verdict'], result['reasoning'])

    # ── COMPREHENSIVE LOGGING: Risk Score + Findings ──
    logger.info(
        f"[SEMANTICGUARD] 🛡️ Evaluation Complete — file={req.filename}, "
        f"verdict={result['verdict']}, risk_score={result['score']:.2f}, "
        f"findings_count={len(result['violations'])}"
    )

    # ── PERFORMANCE LOGGING: Track data transmission ──
    logger.info(
        f"[SEMANTICGUARD] Returning response: action={result['verdict']}, "
        f"drift_score={result['score']:.2f}, raw_output_length={len(result['reasoning'])}"
    )

    # DIAGNOSTIC: expose parser violations for debugging
    logger.info(f"[VIOLATIONS] count={len(result['violations'])}")
    if result['violations']:
        for v in result['violations']:
            logger.info(f"[VIOLATION] {v.get('severity', 'UNKNOWN')} - Line {v.get('line_number', '?')}: {v.get('rule_id', 'NO_RULE')}")
        logger.info(f"[RAW OUTPUT] length={len(result['raw_output'])}")
    return EvaluateResponse(
        action=result['verdict'],
        drift_score=result['score'],
        reasoning=result['reasoning'],
        violations=result['violations'],
        filename=req.filename,
        raw_output=result['raw_output']
    )

# ─── Vault Recovery & Resigning Endpoint ───────────────────────────────────

@app.post("/resign_vault", response_model=ResignResponse, tags=["Security"])
async def resign_vault():
    """Action 1 & 2: Recovery mechanism if the Vault is tampered with."""
    global VAULT_STATE
    root_dir = get_root_dir()  # Explicitly use hardcoded path for main vault
    semanticguard_dir = os.path.join(root_dir, ".semanticguard")
    vault_dir = os.path.join(semanticguard_dir, "semanticguard_vault")
    
    # Overwrite the vault files with Ground-Truth workspace files
    for pillar in PILLARS:
        src = os.path.join(semanticguard_dir, pillar)
        dst = os.path.join(vault_dir, pillar)
        
        if os.path.exists(src):
            shutil.copy2(src, dst)
            with open(dst, "r", encoding="utf-8") as f:
                VAULT_STATE[pillar] = f.read()
        else:
            VAULT_STATE[pillar] = ""
            
    # Generate new SHA-256 hash and lock
    write_vault_lock(root_dir)  # Pass explicit root_dir
    return ResignResponse(status="success", message="Vault cryptographically re-signed.")

# ─── Live Reload: Trigger Sync (The Loophole Fix) ─────────────────────────

class TriggerSyncResponse(BaseModel):
    status: str
    synced_files: list = []
    message: str

@app.post("/trigger_sync", response_model=TriggerSyncResponse, tags=["Security"])
async def trigger_sync():
    """
    Live Reload: Force-compare all Live Pillars against the Vault using MD5
    content hashing. Automatically syncs any differences without requiring
    a server restart. This fixes the 'Vault Initialization Loophole'.
    """
    global VAULT_STATE
    
    _trace_sync_logger.info("TRIGGER_SYNC — Live Reload initiated")
    
    root_dir = get_root_dir()
    semanticguard_dir = os.path.join(root_dir, ".semanticguard")
    vault_dir = os.path.join(semanticguard_dir, "semanticguard_vault")
    
    os.makedirs(vault_dir, exist_ok=True)
    
    synced_files = []
    
    for pillar in PILLARS:
        live_path = os.path.join(semanticguard_dir, pillar)
        vault_path = os.path.join(vault_dir, pillar)
        
        if not os.path.exists(live_path):
            _trace_sync_logger.debug(f"TRIGGER_SYNC — {pillar}: SKIP (live file missing)")
            continue
        
        # Read live content
        with open(live_path, "r", encoding="utf-8") as f:
            live_content = f.read()
        live_hash = hashlib.md5(live_content.encode("utf-8")).hexdigest()
        
        # Read vault content (if it exists)
        vault_hash = ""
        if os.path.exists(vault_path):
            with open(vault_path, "r", encoding="utf-8") as f:
                vault_content = f.read()
            vault_hash = hashlib.md5(vault_content.encode("utf-8")).hexdigest()
        
        if live_hash != vault_hash:
            _trace_sync_logger.info(f"TRIGGER_SYNC — {pillar}: DRIFT DETECTED (live={live_hash[:8]}... vault={vault_hash[:8] if vault_hash else 'MISSING'}...)")
            
            try:
                # Atomic write: tmp then rename
                tmp_path = vault_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(live_content)
                os.replace(tmp_path, vault_path)
                
                # Update in-memory state
                VAULT_STATE[pillar] = live_content
                synced_files.append(pillar)
                
                _trace_sync_logger.info(f"TRIGGER_SYNC — {pillar}: SYNCED ✅")
            except (PermissionError, OSError) as e:
                _trace_sync_logger.critical(f"TRIGGER_SYNC — {pillar}: SYNC FAILED — errno={e.errno}, msg={e.strerror}")
                logger.error(f"Trigger sync failed for {pillar}: {e}")
        else:
            _trace_sync_logger.debug(f"TRIGGER_SYNC — {pillar}: IN SYNC (hash={live_hash[:8]}...)")
    
    # Re-sign the vault if anything changed
    if synced_files:
        try:
            write_vault_lock(root_dir)
            _trace_sync_logger.info(f"TRIGGER_SYNC — Lock re-signed after syncing {len(synced_files)} file(s)")
        except (PermissionError, OSError) as e:
            _trace_sync_logger.critical(f"TRIGGER_SYNC — Lock resign FAILED — errno={e.errno}, msg={e.strerror}")
        
        msg = f"Synced {len(synced_files)} file(s): {', '.join(synced_files)}"
    else:
        msg = "All pillars already in sync. No changes needed."
    
    _trace_sync_logger.info(f"TRIGGER_SYNC COMPLETE — {msg}")
    
    return TriggerSyncResponse(
        status="success",
        synced_files=synced_files,
        message=msg,
    )

def verify_gpu_loading():
    """Verify if the model is loaded into GPU VRAM using nvidia-smi."""
    import subprocess
    import shutil
    import urllib.request
    
    # 1. PING OLLAMA TO ENSURE IT'S RESPONSIVE
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status != 200:
                return False, "Ollama service is not responding correctly."
    except Exception as e:
        return False, f"Ollama service unreachable: {e}"

    # 2. CHECK NVIDIA-SMI FOR VRAM USAGE
    smi = shutil.which("nvidia-smi")
    if not smi:
        return False, "nvidia-smi not found. Cannot verify GPU offloading."
    
    try:
        # Check for processes using GPU
        res = subprocess.run([smi], capture_output=True, text=True, timeout=5, encoding="utf-8")
        if res.returncode != 0:
            return False, "nvidia-smi failed to run."
            
        # ── WSL2 COMPATIBILITY FIX ──
        # In WSL2, nvidia-smi often fails to list individual process names ('ollama' etc)
        # but correctly reports 'Memory-Usage' (e.g. 1742MiB / 8188MiB).
        # We parse the output for ANY significant VRAM usage (>500MiB).
        
        # Look for MiB usage patterns: " 1742MiB / 8188MiB"
        usage_match = re.search(r"(\d+)MiB\s+/\s+(\d+)MiB", res.stdout)
        if usage_match:
            used_vram = int(usage_match.group(1))
            total_vram = int(usage_match.group(2))
            
            # If used VRAM > 500 MiB, we assume the model (or something big) is offloaded.
            # This is safer for WSL2 than looking for the process name.
            if used_vram > 500:
                return True, f"GPU Offloading confirmed via VRAM usage: {used_vram}MiB"
        
        # Fallback: check process list just in case it is working
        if "ollama" in res.stdout.lower() or "llama" in res.stdout.lower():
            return True, "GPU Offloading confirmed via process name."
            
        return False, f"No significant VRAM usage (>500MiB) or Ollama process detected in nvidia-smi. VRAM: {usage_match.group(1) if usage_match else 'ERR'} MiB"
        
    except Exception as e:
        return False, f"GPU verification error: {e}"

# ─── Pillar Evaluation Endpoint ────────────────────────────────────────────

@app.post("/evaluate_pillar", response_model=EvaluateResponse, tags=["Gatekeeper"])
async def evaluate_pillar(req: EvaluatePillarRequest):
    """Evaluate a proposed change to one of the 5 workspace pillars."""
    
    # ── ENTRY-LEVEL TRACE: Log immediately on arrival ──
    _trace_sync_logger.info(f"EVALUATE_PILLAR ENTRY — file: {req.filename}, content_len: {len(req.incoming_content)}, project_path: {req.project_path or 'NOT SET'}")

    # Rule Sanctuary REMOVED here. We MUST evaluate pillars to trigger vault sync.

    # ═══════════════════════════════════════════════════════════════════
    # FIX 1: ATOMIC VAULT SNAPSHOTTING (Pre-Flight Sync)
    # ═══════════════════════════════════════════════════════════════════
    # Before every audit, sync the latest .md files from .semanticguard/ to vault
    # This ensures the AI judges against the ABSOLUTE LATEST architectural laws
    
    global VAULT_STATE
    root_dir = req.project_path if req.project_path else get_root_dir()
    semanticguard_dir = os.path.join(root_dir, ".semanticguard")
    vault_dir = os.path.join(semanticguard_dir, "semanticguard_vault")
    
    os.makedirs(vault_dir, exist_ok=True)
    
    pre_flight_synced = []
    for pillar in PILLARS:
        live_path = os.path.join(semanticguard_dir, pillar)
        vault_path = os.path.join(vault_dir, pillar)
        
        if os.path.exists(live_path):
            # Read live content
            with open(live_path, "r", encoding="utf-8") as f:
                live_content = f.read()
            
            # Check if vault needs update
            needs_sync = False
            if not os.path.exists(vault_path):
                needs_sync = True
            else:
                with open(vault_path, "r", encoding="utf-8") as f:
                    vault_content = f.read()
                if live_content != vault_content:
                    needs_sync = True
            
            if needs_sync:
                # Atomic write to vault
                tmp_path = vault_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(live_content)
                os.replace(tmp_path, vault_path)
                
                # Update in-memory state
                VAULT_STATE[pillar] = live_content
                pre_flight_synced.append(pillar)
                _trace_sync_logger.info(f"PRE-FLIGHT SYNC — {pillar}: UPDATED from live file")
            else:
                # Ensure in-memory state matches vault
                with open(vault_path, "r", encoding="utf-8") as f:
                    VAULT_STATE[pillar] = f.read()
    
    # FIX 4: METADATA VERIFICATION - Log vault state
    rule_count = len(VAULT_STATE.get("system_rules.md", "").split("\n"))
    last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    logger.info(f"[VAULT] Audit triggered using {rule_count} rule lines from {last_updated}")
    if pre_flight_synced:
        logger.info(f"[VAULT] Pre-flight sync updated: {', '.join(pre_flight_synced)}")
    else:
        logger.info(f"[VAULT] All pillars already in sync")
    
    # HARDWARE CHECK: Log GPU status but never block the audit
    gpu_ok, gpu_msg = verify_gpu_loading()
    if not gpu_ok:
        logger.warning(f"GPU check: {gpu_msg} — continuing audit anyway")
    else:
        logger.info(f"GPU check: {gpu_msg}")
    
    if not _model_ready:
        _trace_sync_logger.warning(f"EVALUATE_PILLAR ABORT — model not ready for '{req.filename}'")
        raise HTTPException(status_code=503, detail="SemanticGuard model is still loading.")
        
    # Action 3: Cryptographic Tamper Check (Warning only — does not block audit)
    if not verify_vault_hash(root_dir):
        _trace_sync_logger.warning(f"VAULT HASH MISMATCH detected for '{req.filename}' in '{root_dir}' — proceeding with audit")
        logger.warning(f"🚨 VAULT hash mismatch for {req.filename} — audit continues")


    # Calculate diff
    golden_state = VAULT_STATE.get("golden_state.md", "")
    system_rules = VAULT_STATE.get("system_rules.md", "")
    problems_and_resolutions = VAULT_STATE.get("problems_and_resolutions.md", "")
    current_pillar_content = VAULT_STATE.get(req.filename, "")
    
    # ═══════════════════════════════════════════════════════════════════
    # FIX 5: GROUNDED REASONING - Add Line Numbers & History Status
    # ═══════════════════════════════════════════════════════════════════
    
    # Add line numbers to system_rules for citation enforcement
    def add_line_numbers(content: str, filename: str) -> str:
        """Add line numbers to content for citation enforcement"""
        lines = content.split('\n')
        numbered_lines = []
        for i, line in enumerate(lines, 1):
            numbered_lines.append(f"[{filename}:L{i}] {line}")
        return '\n'.join(numbered_lines)
    
    system_rules_numbered = add_line_numbers(system_rules, "system_rules.md")
    golden_state_numbered = add_line_numbers(golden_state, "golden_state.md")
    
    # FIX 3: History-Zero Validation - Detect empty history
    history_status = "EMPTY"
    if problems_and_resolutions.strip():
        # Check if file has actual content (not just headers/templates)
        content_lines = [line for line in problems_and_resolutions.split('\n') 
                        if line.strip() and not line.startswith('#') and 'No problems' not in line]
        if len(content_lines) > 0:
            history_status = "HAS_ENTRIES"
    
    logger.info(f"[GROUNDING] History status: {history_status}")
    
    diff_lines = list(difflib.unified_diff(
        current_pillar_content.splitlines(),
        req.incoming_content.splitlines(),
        fromfile="current",
        tofile="incoming",
        lineterm=""
    ))
    diff_text = "\n".join(diff_lines)



    # ════════════════════════════════════════════════════════════════════════════════
    # META-GATE EVALUATION FLOW
    # ════════════════════════════════════════════════════════════════════════════════
    
    system_prompt = METAGATE_AUDIT_SYSTEM
    user_prompt = build_meta_gate_prompt(req.filename, current_pillar_content, req.incoming_content)

    t0 = time.perf_counter()
    try:
        # FIX 6: Use /api/chat endpoint with system/user separation
        # OFFLOAD to thread pool to prevent blocking the async event loop during GPU inference
        # Pass processor_mode, model_name, and engine_mode to generate()
        engine_mode = os.environ.get("SEMANTICGUARD_ENGINE_MODE", "local")
        raw = await asyncio.to_thread(generate, user_prompt, system_prompt=system_prompt, processor_mode=req.processor_mode, model_name=req.model_name, engine_mode=engine_mode)

        print("\n" + "="*40)
        print("🏛️ SEMANTICGUARD META-GATE RAW THOUGHTS:")
        print(raw)
        print("="*40 + "\n")
        
    except Exception as e:
        _trace_sync_logger.error(f"EVALUATE_PILLAR INFERENCE CRASHED — file: '{req.filename}', error: {type(e).__name__}: {e}")
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")

    elapsed = time.perf_counter() - t0
    logger.info(f"Meta-Gate eval took {elapsed:.2f}s — file: {req.filename}")
    print(f"\n⏱️ AUDIT TIME (evaluate_pillar): {elapsed:.2f}s\n")

    result = guillotine_parser(raw)
    
    # ── STRIP VOID VIOLATIONS ──
    # If verdict is ACCEPT and score is negligible, clear violations list
    if result['verdict'] == "ACCEPT" and result['score'] < 0.1:
        logger.info(f"🛡️ Stripping void violations for ACCEPT pillar verdict (score: {result['score']})")
        result['violations'] = []

    vault_updated = False
    
    # Append execution to Walkthrough ledger
    append_audit_ledger(result['verdict'], result['reasoning'])

    if result['verdict'] == "ACCEPT":
        _trace_sync_logger.info(f"ACCEPT VERDICT — triggering vault sync for '{req.filename}'")
        print(f"[VAULT SYNC] ACCEPT verdict for '{req.filename}' — syncing to vault at '{root_dir}'...")
        
        try:
            new_hash = sync_and_lock_vault(req.filename, req.incoming_content, root_dir)
            print(f"✅ VAULT SECURED. New Signature: {new_hash}")
            print(f"[VAULT SYNC] Complete ✅ — semanticguard_vault/{req.filename} is now the new baseline.")
            vault_updated = True
        except (PermissionError, OSError) as e:
            _trace_sync_logger.critical(f"VAULT SYNC FAILED for '{req.filename}' — {type(e).__name__}: errno={e.errno}, msg={e.strerror}")
            logger.error(f"Vault sync failed for {req.filename}: {e}")
            raise HTTPException(status_code=500, detail=f"Vault sync failed: {e.strerror} (errno={e.errno})")
    else:
        _trace_sync_logger.info(f"REJECT VERDICT — vault NOT updated for '{req.filename}' (score={result['score']})")

    # ── PERFORMANCE LOGGING: Track data transmission ──
    logger.info(
        f"[SEMANTICGUARD] Returning response: action={result['verdict']}, "
        f"drift_score={result['score']:.2f}, reasoning_length={len(result['reasoning'])}, "
        f"vault_updated={vault_updated}"
    )

    return EvaluateResponse(
        action=result['verdict'],
        drift_score=result['score'],
        reasoning=result['reasoning'],
        violations=result['violations'],
        vault_updated=vault_updated,
        vault_file=req.filename if vault_updated else "",
        filename=req.filename
    )

# ─── Verification Engine Endpoint ──────────────────────────────────────────

@app.post("/verify_intent", response_model=EvaluateResponse, tags=["Validation"])
async def verify_intent(req: VerifyIntentRequest):
    """
    Validates an AI's explanation against the Golden State system rules.
    Acts as a Semantic Lie Detector for the machine intent.
    """
    if not _model_ready:
        raise HTTPException(status_code=503, detail="SemanticGuard model is still loading.")
        
    t0 = time.perf_counter()
    
    root_dir = get_root_dir()
    golden_rules_path = os.path.join(root_dir, ".semanticguard", "system_rules.md")
    
    try:
        result = verify_ai_walkthrough(req.ai_explanation, golden_rules_path)
    except Exception as e:
        logger.error(f"Inference error during intent verify: {e}")
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")
        
    elapsed = time.perf_counter() - t0
    logger.info(f"Intent Validation took {elapsed:.2f}s — Result: {result['verdict']}")
    
    # Append execution to Walkthrough ledger
    append_audit_ledger(result['verdict'], result['reasoning'])
    
    return EvaluateResponse(
        action=result['verdict'],
        drift_score=result['score'],
        reasoning=result['reasoning'],
        vault_updated=False,
    )

@app.post("/audit_reasoning", response_model=EvaluateResponse, tags=["Validation"])
async def audit_reasoning(req: VerifyIntentRequest):
    """
    Closed-Loop Audit: Compares AI reasoning against the Reference Architecture
    in Walkthrough.md to detect hallucinations and context drift.
    """
    if not _model_ready:
        raise HTTPException(status_code=503, detail="SemanticGuard model is still loading.")
        
    t0 = time.perf_counter()
    
    try:
        result = verify_against_ledger(req.ai_explanation)
    except Exception as e:
        logger.error(f"Inference error during closed-loop audit: {e}")
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")
        
    elapsed = time.perf_counter() - t0
    logger.info(f"Closed-Loop Audit took {elapsed:.2f}s — Result: {result['verdict']}")
    
    return EvaluateResponse(
        action=result['verdict'],
        drift_score=result['score'],
        reasoning=result['reasoning'],
        vault_updated=False,
    )

@app.post("/initialize_project", response_model=ResignResponse, tags=["Initialization"])
async def initialize_project(req: InitializeProjectRequest):
    """
    Initialize a SemanticGuard project with a golden template.
    
    Modes:
    - solo-indie: Simple, readable code for solo developers
    - clean-layers: Strict separation of concerns for long-term projects
    - secure-stateless: Maximum security with zero-trust architecture
    """
    if not _model_ready:
        raise HTTPException(status_code=503, detail="SemanticGuard model is still loading.")
    
    logger.info(f"Initializing project at {req.project_path} with mode: {req.mode}")
    
    # Call the initialization function - pass processor_mode
    # Note: we need to update initialize_project_with_template to accept processor_mode
    result = initialize_project_with_template(req.mode, req.project_path, processor_mode=req.processor_mode)
    
    if result['status'] == 'success':
        return ResignResponse(
            status="success",
            message=result['message']
        )
    else:
        # Return the original error message without wrapping
        raise HTTPException(status_code=500, detail=result['message'])

@app.get("/templates", tags=["Initialization"])
async def get_templates():
    """
    Get available golden templates for project initialization.
    """
    return {
        "templates": [
            {
                "id": key,
                "name": template["name"],
                "description": template["description"]
            }
            for key, template in GOLDEN_TEMPLATES.items()
        ]
    }

# ─── Task Management & Memory Evolution Endpoints ──────────────────────────

class MoveTaskRequest(BaseModel):
    task_description: str = Field(..., description="The task text to move from pending to done")
    project_path: str = Field(..., description="Absolute path to the project root directory")
    problems_encountered: str = Field("", description="Optional description of problems faced during this task (for history tracking)")

class EvolveMemoryRequest(BaseModel):
    project_path: str = Field(..., description="Absolute path to the project root directory")

class TaskResponse(BaseModel):
    status: str
    message: str

class MemoryEvolutionResponse(BaseModel):
    status: str
    patterns_added: int
    rules_added: int
    message: str

# ─── Cloud Evaluation Models ────────────────────────────────────────────────

# ─── New Request Model for Context Extraction ──────────────────────────
class ExtractRulesRequest(BaseModel):
    code_snippet: str
    filename: str
    system_rules: str = ""
    model_name: str = "meta-llama/llama-4-scout-17b-16e-instruct"

class BrokenRule(BaseModel):
    rule_id: str
    description: str
    line_number: Optional[int] = None

class ExtractRulesResponse(BaseModel):
    broken_rules: List[BrokenRule]
    tokens_used: int
    latency: float

class EvaluateCloudRequest(BaseModel):
    code_snippet: str = Field(..., description="Content of the file to audit")
    filename: str = Field(..., description="Filename being audited")
    project_path: str = Field("", description="Absolute path to the project root")
    system_rules: str = Field("", description="Contents of .semanticguard/system_rules.md")
    model_name: str = Field("meta-llama/llama-4-scout-17b-16e-instruct", description="Groq model to use")
    prompt_type: str = Field("v2_hardened", description="v2_hardened or stress_test_genius")

class CloudFinding(BaseModel):
    severity: str = Field(..., description="CRITICAL, HIGH, MEDIUM, or LOW")
    vulnerability_type: str = Field(..., description="Type of vulnerability")
    line_number: Optional[int] = Field(None, description="Line number where vulnerability occurs")
    description: str = Field(..., description="Description of the vulnerability")

class EvaluateCloudResponse(BaseModel):
    action: str = Field(..., description="ACCEPT or REJECT")
    findings: List[CloudFinding] = Field(default_factory=list, description="List of security findings")
    reasoning: str = Field("", description="Layer 1 reasoning or cloud audit summary")
    layer: str = Field("", description="Which layer caught it: layer1 or cloud")
    tokens_used: int = Field(0, description="Total tokens consumed by Groq API")
    latency: float = Field(0.0, description="API call latency in seconds")
    risk_score: int = Field(0, description="Layer 1 risk score")
    detected_tpm: int = Field(30000, description="Detected TPM from server bucket")
    detected_rpm: int = Field(30, description="Detected RPM from server bucket")

class AutopsyRequest(BaseModel):
    code_snippet: str = Field(..., description="Vulnerable code that was missed or incorrectly flagged")
    filename: str = Field(..., description="Filename of the vulnerability")
    vulnerability_type: str = Field("Unknown", description="Known category of the vulnerability")
    analysis_mode: str = Field("MISS", description="MISS (False Negative) or FALSE_POSITIVE")
    original_reason: Optional[str] = Field(None, description="The reasoning string why it was flagged (for FP) or should have been flagged (for Miss)")
    model_name: str = Field("meta-llama/llama-4-scout-17b-16e-instruct", description="Groq model to use")
    current_prompt: Optional[str] = Field(None, description="The dynamic rules context (e.g. system_rules.md content)")
    project_path: Optional[str] = Field(None, description="Path to project root to load rules from disk")

class AutopsyResponse(BaseModel):
    suggestion: str = Field(..., description="AI suggestion for golden prompt patch")
    vulnerability_type: str = Field(..., description="Self-corrected vulnerability type")
    bypassed_rule: Optional[str] = Field(None, description="Specific section or rule in the prompt that should have triggered (Phase 2)")
    bypass_reason: Optional[str] = Field(None, description="Why the AI think it bypassed the rule despite its existence (Phase 2)")

@app.post("/move_task", response_model=TaskResponse, tags=["Task Management"])
async def move_task(req: MoveTaskRequest):
    """
    Move a completed task from pending_tasks.md to done_tasks.md.
    Part of the 5 Pillars Evolution Loop with automatic history updates.
    
    EVOLUTIONARY LOGIC: Automatically updates history_phases.md with:
    - Task completion timestamp
    - Problems encountered (if provided)
    - Link to problems_and_resolutions.md for context
    """
    if not _model_ready:
        raise HTTPException(status_code=503, detail="SemanticGuard model is still loading.")
    
    logger.info(f"Moving task: {req.task_description[:50]}...")
    
    try:
        result = move_task_to_done(
            req.task_description, 
            req.project_path,
            req.problems_encountered  # Pass problems for history tracking
        )
        
        if result['status'] == 'success':
            return TaskResponse(
                status="success",
                message=result['message']
            )
        else:
            raise HTTPException(status_code=400, detail=result['message'])
            
    except Exception as e:
        logger.error(f"Task move failed: {e}")
        raise HTTPException(status_code=500, detail=f"Task move failed: {str(e)}")

@app.post("/evolve_memory", response_model=MemoryEvolutionResponse, tags=["Memory Evolution"])
async def evolve_memory(req: EvolveMemoryRequest):
    """
    Trigger the Memory-to-Law Pipeline: Extract patterns from resolved problems
    and negative rules from unresolved problems.
    
    This is the core of the 5 Pillars Evolution Loop that allows SemanticGuard to learn
    from past mistakes and successes.
    """
    if not _model_ready:
        raise HTTPException(status_code=503, detail="SemanticGuard model is still loading.")
    
    logger.info(f"Evolving architectural memory for project: {req.project_path}")
    
    try:
        result = evolve_architectural_memory(req.project_path)
        
        if result['status'] == 'success':
            return MemoryEvolutionResponse(
                status="success",
                patterns_added=result['patterns_added'],
                rules_added=result['rules_added'],
                message=result['message']
            )
        else:
            raise HTTPException(status_code=400, detail=result['message'])
            
    except Exception as e:
        logger.error(f"Memory evolution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Memory evolution failed: {str(e)}")


# ─── Rate Limit Update Endpoint ─────────────────────────────────────────────

class UpdateRateLimitsRequest(BaseModel):
    max_tpm: int = Field(..., description="Detected TPM from API")
    max_rpm: int = Field(..., description="Detected RPM from API")

class UpdateRateLimitsResponse(BaseModel):
    status: str = Field(..., description="success or error")
    message: str = Field(..., description="Status message")
    old_tpm: int = Field(..., description="Previous TPM")
    new_tpm: int = Field(..., description="New TPM")

@app.post("/update_rate_limits", response_model=UpdateRateLimitsResponse, tags=["Cloud Gatekeeper"])
async def update_rate_limits(req: UpdateRateLimitsRequest):
    """
    Update server's TokenBucket with detected TPM/RPM from UI.
    Called by UI before starting folder audit.
    """
    try:
        old_tpm = cloud_rate_limiter.max_tpm
        old_rpm = cloud_rate_limiter.max_rpm
        
        # Only upgrade if detected limits are higher
        if req.max_tpm > cloud_rate_limiter.max_tpm:
            cloud_rate_limiter.max_tpm = req.max_tpm
            cloud_rate_limiter.capacity = req.max_tpm
            cloud_rate_limiter.tokens = req.max_tpm  # ← TOP UP CURRENT TOKENS
            cloud_rate_limiter.refill_rate = req.max_tpm / 60.0
            cloud_rate_limiter.max_file_tokens = min(int(req.max_tpm * 0.2), 100000)
            logger.info(f"🚀 UPGRADED TokenBucket: {old_tpm:,} → {req.max_tpm:,} TPM")
            logger.info(f"🚀 Refill rate: {cloud_rate_limiter.refill_rate:,.0f} tokens/second")
            logger.info(f"🚀 Current tokens topped up: {cloud_rate_limiter.tokens:,}")
        
        if req.max_rpm > cloud_rate_limiter.max_rpm:
            cloud_rate_limiter.max_rpm = req.max_rpm
            logger.info(f"🚀 UPGRADED TokenBucket: {old_rpm} → {req.max_rpm} RPM")
        
        return UpdateRateLimitsResponse(
            status="success",
            message=f"Rate limits updated: {req.max_tpm:,} TPM, {req.max_rpm} RPM",
            old_tpm=old_tpm,
            new_tpm=cloud_rate_limiter.max_tpm
        )
        
    except Exception as e:
        logger.error(f"Failed to update rate limits: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── Cloud Evaluation Endpoint (Thin Client / Fat Server) ──────────────────

@app.post("/evaluate_cloud", response_model=EvaluateCloudResponse, tags=["Cloud Gatekeeper"])
async def evaluate_cloud(req: EvaluateCloudRequest, request: Request):
    """
    Cloud evaluation endpoint - The Fat Server brain for thin client architecture.
    
    Pipeline:
    1. Extract API key from Authorization header
    2. Run Layer 1 Pre-Screener (exploitability-based filtering)
    3. If Layer 1 rejects → return immediately
    4. If Layer 1 passes → call Groq API with golden 98% accuracy prompt
    5. Parse findings and return standardized response
    
    This endpoint consolidates all the golden logic from stress_test.py:
    - Layer1PreScreener for pre-filtering
    - TokenBucket for rate limiting
    - Golden system prompt for 98% accuracy
    - Groq API integration with retry logic
    """
    async with global_eval_semaphore:
        start_time = time.time()
    
        # ─── STEP 1: Extract API Key ───────────────────────────────────────────
        api_key = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]  # Remove "Bearer " prefix
        
        if not api_key:
            logger.error("Cloud evaluation: Missing API key in Authorization header")
            raise HTTPException(
                status_code=401,
                detail="Missing API key. Please provide Authorization: Bearer <api_key> header."
            )
        
        logger.info(f"Cloud evaluation: {req.filename} (API key length: {len(api_key)})")
        
        # ─── STEP 2: Run Layer 1 Pre-Screener ──────────────────────────────────
        file_extension = os.path.splitext(req.filename)[1]
        
        # BYPASS: If system_rules are provided, we MUST audit even if the file is small
        # This ensures rules like "No print" are caught even in 1-line files.
        if req.system_rules:
            logger.info(f"Layer 1 Pre-Screener: BYPASS (Local rules provided)")
            should_audit, reason, risk_score = True, "Context-Aware Override", 1.0
        else:
            should_audit, reason, risk_score = CloudLayer1PreScreener.should_audit(
                code=req.code_snippet,
                file_extension=file_extension,
                filename=req.filename
            )
        
        if not should_audit:
            logger.info(f"Layer 1 Pre-Screener: SKIP - {reason}")
            return EvaluateCloudResponse(
                action="ACCEPT",
                findings=[],
                reasoning=f"Layer 1 Pre-Screener: {reason}",
                layer="layer1",
                tokens_used=0,
                latency=time.time() - start_time,
                risk_score=risk_score,
                detected_tpm=cloud_rate_limiter.max_tpm,
                detected_rpm=cloud_rate_limiter.max_rpm
            )
        
        logger.info(f"Layer 1 Pre-Screener: PASS - Risk score: {risk_score}")
    
        # ─── STEP 3: Prepare Code with Line Numbers ────────────────────────────
        # Prepend line numbers to every line so the LLM can reference them precisely
        numbered_lines = [f"{i+1}: {line}" for i, line in enumerate(req.code_snippet.splitlines())]
        numbered_code = "\n".join(numbered_lines)
        
        # ─── STEP 4: Load Project-Specific Rules & Prompt ──────────────────────
        dynamic_rules = ""
        if req.project_path:
            rules_path = os.path.join(req.project_path, ".semanticguard", "system_rules.md")
            try:
                with open(rules_path, 'r', encoding='utf-8') as f:
                    dynamic_rules = f.read().strip()
                logger.info(f"Loaded {len(dynamic_rules)} chars from system_rules.md")
            except FileNotFoundError:
                logger.debug("No system_rules.md found - using default rules")
        
        # Build Golden System Prompt first so we can accurately measure its length
        system_prompt = get_hardened_system_prompt(dynamic_rules, req.prompt_type)
        user_prompt = f"Audit this code (each line prefixed with its line number):\n\n{numbered_code}"

        # ─── STEP 5: Token Estimation and Rate Limiting ────────────────────────
        # Accurately detect tokens: count words/punctuation for BPE approximation
        # Matches Groq's BPE logic much more closely than simple char-division
        system_prompt_tokens = len(re.findall(r"\w+|[^\w\s]", system_prompt))
        code_tokens = len(re.findall(r"\w+|[^\w\s]", req.code_snippet))
        output_reserve = 500  # Matches "max_tokens": 500 in STEP 7
        estimated_tokens = system_prompt_tokens + code_tokens + output_reserve
        
        logger.info(f"AUDITING {req.filename} | Detected Tokens: {estimated_tokens:,} (Prompt: {system_prompt_tokens:,} + Code: {code_tokens:,} + Output: {output_reserve})")
        
        # Check if file is too large
        if estimated_tokens > cloud_rate_limiter.max_file_tokens:
            logger.warning(f"File too large: {estimated_tokens:,} tokens > {cloud_rate_limiter.max_file_tokens:,} max")
            return EvaluateCloudResponse(
                action="ACCEPT",
                findings=[],
                reasoning=f"File too large ({estimated_tokens:,} tokens). Skipped cloud audit.",
                layer="layer1",
                tokens_used=0,
                latency=time.time() - start_time,
                risk_score=risk_score,
                detected_tpm=cloud_rate_limiter.max_tpm,
                detected_rpm=cloud_rate_limiter.max_rpm
            )
        
        # Wait for token availability (global rate limiting)
        wait_time = await cloud_rate_limiter.consume_with_wait(estimated_tokens)
        
        if wait_time > 0:
            logger.info(f"Rate limiting: Waited {wait_time:.2f}s for {estimated_tokens:,} tokens")
        
        # ─── GLOBAL PAUSE DOUBLE-CHECK (Race Condition Prevention) ─────────────
        # After waking from sleep, check if another request triggered a global pause
        while cloud_rate_limiter.global_pause_until and time.time() < cloud_rate_limiter.global_pause_until:
            pause_remaining = cloud_rate_limiter.global_pause_until - time.time()
            if pause_remaining > 0:
                logger.warning(f"Request woke up but global pause is active. Sleeping for {pause_remaining:.2f}s")
                await asyncio.sleep(pause_remaining)
    
        # ─── STEP 7: Call Groq API with Retry Logic ────────────────────────────
        max_retries = 3
        retry_count = 0
        groq_endpoint = "https://api.groq.com/openai/v1/chat/completions"
        
        while retry_count <= max_retries:
            try:
                api_start = time.time()
                
                # ═══ THUNDERING HERD PREVENTION: Semaphore-controlled HTTP call ═══
                # Even if 10 requests wake from sleep simultaneously, only 3 can call Groq at once
                async with groq_outbound_semaphore:
                    response = await asyncio.to_thread(
                        requests.post,
                        groq_endpoint,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": req.model_name,
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
                
                api_latency = time.time() - api_start
                
                # Handle HTTP errors
                if response.status_code != 200:
                    # Refund tokens on error
                    cloud_rate_limiter.refund(estimated_tokens, 0)
                    
                    # Special handling for 429 (rate limit)
                    if response.status_code == 429:
                        if retry_count < max_retries:
                            retry_count += 1
                            await cloud_rate_limiter.set_global_pause(30.0)
                            logger.warning(f"429 Rate Limit! Detail: {response.text[:500]}")
                            logger.warning(f"Global pause 30s, retry {retry_count}/{max_retries}")
                            await asyncio.sleep(30)
                            continue
                        else:
                            raise HTTPException(
                                status_code=429,
                                detail=f"Groq rate limit exceeded after {max_retries} retries"
                            )
                    
                    # Retry on timeout errors (408, 504)
                    if response.status_code in [408, 504] and retry_count < max_retries:
                        retry_count += 1
                        logger.warning(f"HTTP {response.status_code} timeout, retry {retry_count}/{max_retries}")
                        await asyncio.sleep(15)
                        continue
                    
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Groq API error: {response.text[:200]}"
                    )
                
                # ─── STEP 8: Parse Groq Response ───────────────────────────────
                data = response.json()
                tokens_used = data.get("usage", {}).get("total_tokens", estimated_tokens)
                result_content = data["choices"][0]["message"]["content"]
                
                # Refund difference if actual is lower than estimate
                cloud_rate_limiter.refund(estimated_tokens, tokens_used)
                
                logger.info(f"Groq API success: {tokens_used:,} tokens, {api_latency:.2f}s latency")
                
                # ─── STEP 9: Parse Findings ────────────────────────────────────
                try:
                    parsed = json.loads(result_content.strip())
                    
                    # Normalize findings to a list
                    findings_raw = []
                    if isinstance(parsed, list):
                        findings_raw = parsed
                    elif isinstance(parsed, dict):
                        findings_raw = parsed.get("findings", [])
                        # Handle stringified array
                        if isinstance(findings_raw, str) and findings_raw.strip().startswith("["):
                            try:
                                findings_raw = json.loads(findings_raw)
                            except:
                                findings_raw = []
                        # Fallback to single-object schema
                        if (not findings_raw or not isinstance(findings_raw, list)) and "is_vulnerable" in parsed:
                            findings_raw = [parsed]
                    
                    if not isinstance(findings_raw, list):
                        findings_raw = []
                    
                    # Convert to CloudFinding objects
                    findings = []
                    for finding in findings_raw:
                        if not isinstance(finding, dict):
                            continue
                        if finding.get("is_vulnerable") is True:
                            findings.append(CloudFinding(
                                severity=str(finding.get("severity", "UNKNOWN")).upper(),
                                vulnerability_type=str(finding.get("vulnerability_type", "Unknown Vulnerability")),
                                line_number=finding.get("line_number"),
                                description=str(finding.get("description", "No description provided."))
                            ))
                    
                    # Determine action
                    action = "REJECT" if findings else "ACCEPT"
                    
                    total_latency = time.time() - start_time
                    
                    logger.info(f"Cloud evaluation complete: {action} with {len(findings)} finding(s)")
                    
                    return EvaluateCloudResponse(
                        action=action,
                        findings=findings,
                        reasoning=f"Cloud audit via {req.model_name}: {len(findings)} finding(s) detected" if findings else "Cloud audit: No vulnerabilities detected",
                        layer="cloud",
                        tokens_used=tokens_used,
                        latency=total_latency,
                        risk_score=risk_score,
                        detected_tpm=cloud_rate_limiter.max_tpm,
                        detected_rpm=cloud_rate_limiter.max_rpm
                    )
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parse error: {str(e)[:100]}")
                    logger.error(f"Raw response: {result_content[:500]}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to parse Groq response: {str(e)[:100]}"
                    )
            
            except (requests.Timeout, asyncio.TimeoutError) as e:
                if retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"Timeout! Retry {retry_count}/{max_retries}")
                    await asyncio.sleep(15)
                    continue
                
                logger.error(f"Timeout after {max_retries} retries")
                raise HTTPException(
                    status_code=504,
                    detail=f"Groq API timeout after {max_retries} retries"
                )
            
            except Exception as e:
                logger.error(f"Cloud evaluation error: {str(e)[:200]}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Cloud evaluation failed: {str(e)[:200]}"
                )
    
        # Should never reach here
        raise HTTPException(
            status_code=500,
            detail="Unknown error in cloud evaluation"
        )

@app.post("/extract_rules", response_model=ExtractRulesResponse, tags=["Cloud Gatekeeper"])
async def extract_rules(req: ExtractRulesRequest, request: Request):
    """
    Context Extraction Endpoint - Lightweight 'Vibe Coder' architecture extractor.
    """
    async with global_eval_semaphore:
        start_time = time.time()
    
        # ─── STEP 1: Extract API Key ───────────────────────────────────────────
        api_key = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
        
        if not api_key:
            logger.error("Context extraction: Missing API key in Authorization header")
            raise HTTPException(
                status_code=401,
                detail="Missing API key. Please provide Authorization: Bearer <api_key> header."
            )
        
        logger.info(f"Context extraction: {req.filename} (API key length: {len(api_key)})")
        
        # ─── STEP 2: Prepare Prompt (Phase 3 Precision Upgrade) ───────────────
        # Add line numbers to the code snippet for precise referencing
        numbered_code = "\n".join([f"{i+1} | {line}" for i, line in enumerate(req.code_snippet.splitlines())])
        
        system_prompt = get_drift_detection_prompt(req.system_rules)
        user_prompt = f"Analyze this file ({req.filename}). Did it violate any of the provided system rules?\n\n{numbered_code}"

        # ─── STEP 3: Token Estimation and Rate Limiting ────────────────────────
        # LIGHTWEIGHT FORMULA: (chars // 4 + output_reserve) * 1.15 safety tax
        output_reserve = 800
        estimated_tokens = int(((len(system_prompt) + len(req.code_snippet)) // 4 + output_reserve) * 1.15)
        
        logger.info(f"EXTRACTING RULES {req.filename} | Estimated Tokens: {estimated_tokens:,}")
        
        # Wait for token availability (global rate limiting)
        wait_time = await cloud_rate_limiter.consume_with_wait(estimated_tokens)
        
        if wait_time > 0:
            logger.info(f"Rate limiting: Waited {wait_time:.2f}s for {estimated_tokens:,} tokens")
        
        # ─── GLOBAL PAUSE DOUBLE-CHECK (Race Condition Prevention) ─────────────
        while cloud_rate_limiter.global_pause_until and time.time() < cloud_rate_limiter.global_pause_until:
            pause_remaining = cloud_rate_limiter.global_pause_until - time.time()
            if pause_remaining > 0:
                logger.warning(f"Extracted Rules request woke up but global pause is active. Sleeping for {pause_remaining:.2f}s")
                await asyncio.sleep(pause_remaining)
    
        # ─── STEP 4: Call Groq API with Retry Logic ────────────────────────────
        max_retries = 3
        retry_count = 0
        groq_endpoint = "https://api.groq.com/openai/v1/chat/completions"
        
        while retry_count <= max_retries:
            try:
                api_start = time.time()
                
                # Semaphore-controlled HTTP call
                async with groq_outbound_semaphore:
                    response = await asyncio.to_thread(
                        requests.post,
                        groq_endpoint,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": req.model_name,
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
                
                api_latency = time.time() - api_start
                
                # Handle HTTP errors
                if response.status_code != 200:
                    cloud_rate_limiter.refund(estimated_tokens, 0)
                    
                    if response.status_code == 429:
                        if retry_count < max_retries:
                            retry_count += 1
                            await cloud_rate_limiter.set_global_pause(30.0)
                            logger.warning(f"429 Rate Limit in Extraction! Retry {retry_count}/{max_retries}")
                            await asyncio.sleep(30)
                            continue
                        else:
                            raise HTTPException(status_code=429, detail="Groq rate limit exceeded after retries")
                    
                    if response.status_code in [408, 504] and retry_count < max_retries:
                        retry_count += 1
                        logger.warning(f"HTTP {response.status_code} timeout, retry {retry_count}/{max_retries}")
                        await asyncio.sleep(15)
                        continue
                    
                    raise HTTPException(status_code=response.status_code, detail=f"Groq API error: {response.text[:200]}")
                
                # ─── STEP 5: Parse Groq Response ───────────────────────────────
                data = response.json()
                tokens_used = data.get("usage", {}).get("total_tokens", estimated_tokens)
                result_content = data["choices"][0]["message"]["content"]
                
                # Refund difference
                cloud_rate_limiter.refund(estimated_tokens, tokens_used)
                
                logger.info(f"Extraction success: {tokens_used:,} tokens, {api_latency:.2f}s latency")
                
                try:
                    parsed = json.loads(result_content.strip())
                    broken_rules = parsed.get("broken_rules", [])
                    
                    total_latency = time.time() - start_time
                    return ExtractRulesResponse(
                        broken_rules=broken_rules,
                        tokens_used=tokens_used,
                        latency=total_latency
                    )
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Extraction JSON parse error: {str(e)[:100]}")
                    raise HTTPException(status_code=500, detail=f"Failed to parse extraction response: {str(e)[:100]}")
            
            except (requests.Timeout, asyncio.TimeoutError) as e:
                if retry_count < max_retries:
                    retry_count += 1
                    await asyncio.sleep(15)
                    continue
                raise HTTPException(status_code=504, detail="Groq API timeout after retries")
            
            except Exception as e:
                logger.error(f"Context extraction error: {str(e)[:200]}")
                raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)[:200]}")
    
        raise HTTPException(status_code=500, detail="Unknown error in extraction")

@app.post("/run_autopsy", response_model=AutopsyResponse, tags=["Cloud Gatekeeper"])
async def run_autopsy(req: AutopsyRequest, request: Request):
    """
    Self-Healing Prompt Loop: Analyzes a missed vulnerability and suggests a patch 
    for the Golden System Prompt.
    """
    # Extract API Key
    api_key = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]
    
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    # Load dynamic rules for context
    dynamic_rules = req.current_prompt if req.current_prompt else ""
    
    # If project_path is provided, try to load rules from disk as fallback/override
    if req.project_path:
        rules_path = os.path.join(req.project_path, ".semanticguard", "system_rules.md")
        try:
            if os.path.exists(rules_path):
                with open(rules_path, 'r', encoding='utf-8') as f:
                    disk_rules = f.read().strip()
                    if disk_rules:
                        dynamic_rules = disk_rules
                        logger.info(f"Autopsy: Loaded {len(dynamic_rules)} chars from system_rules.md on disk")
        except Exception as e:
            logger.warning(f"Autopsy: Failed to load rules from disk: {e}")

    # ALWAYS construct the FULL golden prompt so the Meta-LLM sees the exact same rules as the auditor
    golden_prompt = get_hardened_system_prompt(dynamic_rules)
    
    logger.info(f"Running autopsy for {req.filename} ({req.analysis_mode}) using reconstructed Golden Prompt")

    if req.analysis_mode == "FALSE_POSITIVE":
        meta_prompt = f"""You are a Meta-Prompt Engineer for SemanticGuard.
The following Golden System Prompt incorrectly flagged a SAFE file as vulnerable (FALSE POSITIVE).

[INCORRECT REASONING GIVEN BY AI]
{req.original_reason}

[GOLDEN SYSTEM PROMPT]
{golden_prompt}

[SAFE CODE - {req.filename}]
{req.code_snippet}

YOUR MISSION:
1. Explain why the Golden System Prompt incorrectly flagged this safe code.
2. Identify WHICH SPECIFIC RULE or SECTION in the [GOLDEN SYSTEM PROMPT] was responsible for this false positive.
3. Suggest a precise 1-2 sentence modification or exclusion rule to prevent this specific False Positive.
4. Explain WHY the AI triggered this rule despite it being safe code.

MANDATORY: You MUST output valid JSON in this exact format: 
{{
  "suggestion": "your 1-2 sentence fix here", 
  "vulnerability_type": "False Positive - {req.vulnerability_type}",
  "bypassed_rule": "The specific rule label or section header that triggered",
  "bypass_reason": "Explanation of the logic failure for this false positive"
}}.
"""
    else:
        meta_prompt = f"""You are a Meta-Prompt Engineer for SemanticGuard.
The following Golden System Prompt FAILED to detect a CRITICAL vulnerability in the provided code (MISS).

[KNOWN VULNERABILITY TYPE]
{req.vulnerability_type}

[ORIGINAL GROUND TRUTH CONTEXT]
{req.original_reason if req.original_reason else "Vulnerable code missed during regular audit."}

[GOLDEN SYSTEM PROMPT]
{golden_prompt}

[VULNERABLE CODE - {req.filename}]
{req.code_snippet}

YOUR MISSION:
1. This code IS VULNERABLE to {req.vulnerability_type}. You MUST identify exactly how it bypassed the Golden System Prompt.
2. Locate the EXACT SECTION or RULE in the [GOLDEN SYSTEM PROMPT] that SHOULD have caught this (e.g., SECTION ZERO, RULE_101, etc.).
3. Explain WHY the AI failed to trigger that rule (e.g., "Taint path was too deep", "Rule was too vague", "Attention saturation").
4. Suggest a precise 1-2 sentence rule or Regex pattern that MUST be added to the Golden Prompt to ensure this is caught.

MANDATORY: You MUST output valid JSON in this exact format: 
{{
  "suggestion": "your 1-2 sentence rule here", 
  "vulnerability_type": "{req.vulnerability_type}",
  "bypassed_rule": "The section header or Rule ID that failed to trigger",
  "bypass_reason": "Detailed analysis of why the LLM ignored/bypassed the existing rule"
}}.
"""

    try:
        response = await asyncio.to_thread(
            requests.post,
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": req.model_name,
                "messages": [
                    {"role": "system", "content": "You are a professional security researcher and prompt engineer. You only communicate via valid JSON."},
                    {"role": "user", "content": meta_prompt}
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"}
            },
            timeout=45
        )

        if not response.ok:
            raise HTTPException(status_code=response.status_code, detail=f"Autopsy failed: {response.text}")

        try:
            data = response.json()
            raw_content = data["choices"][0]["message"]["content"]
            result = json.loads(raw_content)
            
            return AutopsyResponse(
                suggestion=result.get("suggestion", "No suggestion provided."),
                vulnerability_type=result.get("vulnerability_type", "Unknown"),
                bypassed_rule=result.get("bypassed_rule", "None identified"),
                bypass_reason=result.get("bypass_reason", "No reason provided")
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Autopsy AI Hallucination: {str(e)}")
            logger.error(f"Raw response text: {response.text}")
            raise HTTPException(
                status_code=500,
                detail=f"AI returned malformed JSON. Raw text: {response.text[:500]}"
            )

    except Exception as e:
        logger.error(f"Autopsy error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
