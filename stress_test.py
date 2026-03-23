#!/usr/bin/env python3
"""
🛡️ Trepan Enterprise Stress Test
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

# ─── ANSI Color Codes ────────────────────────────────────────────────────────

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

# ─── Configuration ──────────────────────────────────────────────────────────

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
    }
}

# ─── Token Bucket Rate Limiter ──────────────────────────────────────────────

class TokenBucket:
    """Global Leaky Bucket Rate Limiter with asyncio.Lock()
    
    Prevents concurrent task bursts by maintaining globally shared token state.
    Tokens regenerate at 500/second (30,000 TPM).
    Uses asyncio.Lock() to serialize token consumption.
    """
    
    def __init__(self, max_rpm: int, max_tpm: int):
        self.max_rpm = max_rpm
        self.max_tpm = max_tpm
        self.available_tokens = max_tpm  # Start with full bucket
        self.last_refill = time.time()
        self.refill_rate = max_tpm / 60  # Tokens per second (500 for 30k TPM)
        
        # Asyncio lock for thread-safe token consumption
        self.lock = asyncio.Lock()
        
        # Global 429 cooldown flag
        self.global_pause_until = 0.0
        self.global_pause_lock = asyncio.Lock()
        
        # Tracking
        self.token_history = deque(maxlen=60)
        self.rate_limit_hit_time = None
        self.rate_limit_recovery_time = 10
        self.safety_buffer = 1.10
        
        # Skip threshold for files too large
        self.max_file_tokens = 25000
    
    def refill(self):
        """Refill available tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill
        
        # Add tokens: elapsed_seconds * refill_rate
        tokens_to_add = elapsed * self.refill_rate
        self.available_tokens = min(self.max_tpm, self.available_tokens + tokens_to_add)
        
        self.last_refill = now
    
    async def set_global_pause(self, duration: float = 30.0):
        """Set global pause flag when 429 error occurs"""
        async with self.global_pause_lock:
            self.global_pause_until = time.time() + duration
    
    async def wait_for_global_pause(self):
        """Wait if global pause is active"""
        async with self.global_pause_lock:
            pause_remaining = self.global_pause_until - time.time()
        
        if pause_remaining > 0:
            await asyncio.sleep(pause_remaining)
    
    async def consume(self, file_tokens: int) -> Tuple[bool, float]:
        """Consume tokens from the global bucket with exact delay calculation.
        
        Returns: (success, wait_time)
        - success: True if tokens were consumed
        - wait_time: How long we waited (for logging)
        """
        # Check if file is too large
        if file_tokens > self.max_file_tokens:
            return False, 0.0  # Signal to skip this file
        
        # Wait for global pause to end
        await self.wait_for_global_pause()
        
        async with self.lock:
            # Refill based on elapsed time
            self.refill()
            
            # If we have enough tokens, consume immediately
            if self.available_tokens >= file_tokens:
                self.available_tokens -= file_tokens
                self.token_history.append((time.time(), file_tokens))
                return True, 0.0
            
            # Calculate exact delay needed to refill deficit
            deficit = file_tokens - self.available_tokens
            delay_seconds = (deficit / self.refill_rate) * self.safety_buffer
            
            # Return delay (caller will sleep)
            return False, delay_seconds
    
    async def consume_with_wait(self, file_tokens: int) -> float:
        """Consume tokens, waiting if necessary. Returns actual wait time.
        
        This is the main method called by audit_file.
        """
        # Check if file is too large
        if file_tokens > self.max_file_tokens:
            return -1.0  # Signal to skip this file
        
        # Try to consume
        success, wait_time = await self.consume(file_tokens)
        
        if success:
            return 0.0  # No wait needed
        
        # Wait for tokens to refill
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        
        # Try again after waiting
        success, _ = await self.consume(file_tokens)
        
        if success:
            return wait_time
        
        # Fallback: wait a bit more and try once more
        await asyncio.sleep(1.0)
        success, _ = await self.consume(file_tokens)
        
        if success:
            return wait_time + 1.0
        
        # Should not reach here, but return the calculated wait
        return wait_time
    
    def on_rate_limit_error(self):
        """Called when a 429 error is received"""
        self.rate_limit_hit_time = time.time()
        self.available_tokens = 0  # Reset bucket
    
    def get_recovery_wait_time(self) -> float:
        """Get how long to wait after a 429 error"""
        if self.rate_limit_hit_time is None:
            return 0.0
        
        elapsed = time.time() - self.rate_limit_hit_time
        remaining = self.rate_limit_recovery_time - elapsed
        
        if remaining <= 0:
            self.rate_limit_hit_time = None
            return 0.0
        
        return remaining
    
    def can_request(self, estimated_tokens: int = 1000) -> Tuple[bool, float]:
        """Legacy method for backward compatibility"""
        recovery_wait = self.get_recovery_wait_time()
        if recovery_wait > 0:
            return False, recovery_wait
        
        self.refill()
        
        if estimated_tokens > self.max_tpm:
            raise ValueError(f"File too large ({estimated_tokens} tokens) for TPM limit ({self.max_tpm})")
        
        if self.available_tokens >= estimated_tokens:
            self.available_tokens -= estimated_tokens
            return True, 0.0
        
        rpm_wait = (1 - (self.max_rpm / 60)) * (60 / self.max_rpm) if (self.max_rpm / 60) < 1 else 0
        tpm_wait = (estimated_tokens - self.available_tokens) * (60 / self.max_tpm) if self.available_tokens < estimated_tokens else 0
        
        wait_time = max(rpm_wait, tpm_wait)
        return False, wait_time
    
    def refund(self, tokens_estimated: int, tokens_actual: int):
        """Refund tokens if estimate was too high"""
        if tokens_estimated > tokens_actual:
            self.available_tokens = min(self.max_tpm, self.available_tokens + (tokens_estimated - tokens_actual))
    
    def consume_legacy(self, tokens_used: int):
        """Legacy method for backward compatibility"""
        self.token_history.append((time.time(), tokens_used))

# ─── Layer 1 Pre-Screener (AST/Regex) ──────────────────────────────────────

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
        "css": r"(?i)(style|css|theme|color|icon|view|ui|component|button|input|label|modal|dialog|panel|sidebar|toolbar|menu|widget)",
        "test": r"(?i)(test|spec|mock|fixture|stub)",
        "doc": r"(?i)(readme|doc|example|sample|demo)",
    }
    
    # Hard skip: low-risk content keywords
    SAFE_CONTENT_KEYWORDS = {
        "css_content": r"(?i)(\.css|@media|@keyframes|background-color|border-radius|font-size|padding|margin)",
        "theme_content": r"(?i)(theme|color|palette|dark|light|accent|primary|secondary)",
        "ui_content": r"(?i)(react|vue|angular|component|render|jsx|tsx|html|dom)",
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
    
    # SYSTEM KEYWORDS: +2 pts each (system/network access - needs context)
    SYSTEM_KEYWORDS = {
        "spawn": r"\bspawn\s*\(",
        "subprocess": r"\bsubprocess\.",
        "fs": r"\bfs\.",
        "process": r"\bprocess\.",
        "http": r"(?i)(http|https|request|response)",
        "path_join": r"\bpath\.join",
        "require_fs": r"require\s*\(\s*['\"]fs['\"]",
        "require_child": r"require\s*\(\s*['\"]child_process['\"]",
        "fetch": r"\bfetch\s*\(",
        "axios": r"\baxios\.",
        "database": r"(?i)(database|sql|query|connection|pool)",
        "auth": r"(?i)(authenticate|authorize|permission|role|access)",
        "crypto": r"(?i)(crypto|encrypt|decrypt|hash|sign|verify)",
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

# ─── File Scanner ──────────────────────────────────────────────────────────

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
        print(f"\n{colored('🔍 Scanning codebase...', Colors.CYAN)}")
        
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
        
        print(f"{colored(f'✓ Found {len(self.files)} high-risk files', Colors.GREEN)}")
        print(f"{colored(f'⊘ Filtered {len(self.skipped_files)} files (safe/boilerplate)', Colors.DIM)}")
        return self.files

# ─── Groq API Client ────────────────────────────────────────────────────────

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
        return """You are an AGGRESSIVE AppSec auditor focused on EXPLOITABILITY, not patterns.

Your job is to find REAL, EXPLOITABLE security issues. Avoid false positives.

═══════════════════════════════════════════════════════════════════════════════

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

═══════════════════════════════════════════════════════════════════════════════

ENVIRONMENT VARIABLE INJECTION:

Only flag HIGH severity if:
- env contains execution-influencing variables (LD_PRELOAD, BASH_ENV, ZDOTDIR, PYTHONPATH, NODE_OPTIONS)
AND
- those variables are derived from untrusted input

Otherwise:
- Classify as LOW or ignore

Example (DO NOT FLAG):
  spawn('node', ['app.js'], { env: process.env })  // Safe: env is from trusted process

Example (FLAG as HIGH):
  spawn('node', ['app.js'], { env: { PYTHONPATH: userInput } })  // Unsafe: user controls PYTHONPATH

═══════════════════════════════════════════════════════════════════════════════

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
   - Hardcoded API keys, tokens, passwords, secrets
   - Credentials in environment variable defaults
   - Secrets in test files (even in /tests/ folder)
   - Private keys or certificates in code

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

═══════════════════════════════════════════════════════════════════════════════

IMPORTANT RULES:

- Do NOT assume user control unless explicitly shown in the code
- Do NOT flag safe patterns without a real attack path
- Prefer LOW severity over false positives
- Shift from pattern-based detection to exploitability-based reasoning

OUTPUT FORMAT (REQUIRED):

If you find ANY EXPLOITABLE vulnerability, respond with:
VULNERABILITY_FOUND: [SEVERITY] [TYPE] at line [N]: [1-line description]

If the code is completely safe (no exploitable issues), respond with:
SAFE - No exploitable vulnerabilities detected.

Be AGGRESSIVE about exploitability. Be CONSERVATIVE about false positives."""
    
    async def audit_file(self, file_path: Path) -> Dict:
        """Audit a single file with global leaky bucket rate limiting
        
        Uses globally shared token state with asyncio.Lock() to prevent bursts.
        Skips files > 25,000 tokens (too large for free tier).
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
        
        # Estimate tokens (rough: 1 token ≈ 4 chars)
        estimated_tokens = len(code) // 4 + 500
        
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
        
        # GLOBAL LEAKY BUCKET: Wait for token availability
        wait_time = await self.rate_limiter.consume_with_wait(estimated_tokens)
        
        # Print throttling info with timestamp
        if wait_time > 0:
            timestamp = get_timestamp()
            print(f"{colored(f'[{timestamp}] [Wait: {wait_time:.2f}s for {estimated_tokens:,} tokens]', Colors.CYAN)}")
        
        while retry_count <= max_retries:
            try:
                # Make API call (non-blocking via asyncio.to_thread)
                start_time = time.time()
                
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
                            {"role": "system", "content": self.get_system_prompt()},
                            {"role": "user", "content": f"Audit this code:\n\n{code}"}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 500
                    },
                    timeout=60
                )
                
                elapsed = time.time() - start_time
                
                if response.status_code != 200:
                    # Refund tokens on error
                    self.rate_limiter.refund(estimated_tokens, 0)
                    
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
                self.rate_limiter.refund(estimated_tokens, tokens_used)
                self.total_tokens += tokens_used
                self.files_scanned += 1
                
                # Parse result
                result_upper = result.strip().upper()
                is_vulnerable = (
                    "VULNERABILITY_FOUND" in result_upper and
                    not any(word in result_upper for word in ["SAFE", "NO VULNERABILITIES", "NOT VULNERABLE"])
                )
                
                if is_vulnerable:
                    lines = result.strip().split('\n')
                    violation_summary = lines[0] if lines else result.strip()[:100]
                    
                    self.vulnerabilities_found.append({
                        "file": str(file_path),
                        "finding": result,
                        "summary": violation_summary
                    })
                
                return {
                    "file": str(file_path),
                    "status": "vulnerable" if is_vulnerable else "safe",
                    "finding": result if is_vulnerable else None,
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
        print(f"\n{colored('🚀 Starting audit...', Colors.CYAN)}")
        print(f"{colored(f'Model: {self.model} | Max RPM: {self.rate_limiter.max_rpm} | Max TPM: {self.rate_limiter.max_tpm}', Colors.DIM)}\n")
        
        def get_timestamp():
            """Get current timestamp with milliseconds"""
            now = datetime.now()
            return now.strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
        
        def estimate_tokens(file_path: Path) -> int:
            """Estimate tokens for a file (1 token ≈ 4 chars)"""
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
                tokens_before = tokens_processed["count"]
                
                # Print progress indicator with timestamp and token info
                print(f"{colored(f'[{timestamp}] [{current}/{total_files}]', Colors.CYAN)} {colored(file_path.name, Colors.DIM)} {colored(f'[{tokens_before:,}/{total_tokens_estimate:,} Tokens | File: {file_token_count:,}]', Colors.YELLOW)}")
                
                result = await self.audit_file(file_path)
                
                # Update tokens processed
                tokens_processed["count"] += file_token_count
                
                return result
        
        tasks = [audit_with_semaphore(f) for f in files]
        results = await asyncio.gather(*tasks)
        
        return results

# ─── Terminal UI ────────────────────────────────────────────────────────────

def print_header():
    print(f"\n{colored('╔════════════════════════════════════════════════════════════╗', Colors.BOLD)}")
    print(f"{colored('║', Colors.BOLD)}  {colored('🛡️  TREPAN ENTERPRISE STRESS TEST', Colors.BOLD)}  {colored('║', Colors.BOLD)}")
    print(f"{colored('║', Colors.BOLD)}  {colored('Zero-Shot Security Audit via Groq', Colors.DIM)}  {colored('║', Colors.BOLD)}")
    print(f"{colored('╚════════════════════════════════════════════════════════════╝', Colors.BOLD)}\n")

def get_api_key() -> str:
    """Prompt for API key securely"""
    print(f"{colored('🔑 Enter your Groq API Key (hidden):', Colors.CYAN)}")
    api_key = getpass.getpass("→ ")
    if not api_key:
        print(f"{colored('❌ API key cannot be empty', Colors.RED)}")
        sys.exit(1)
    return api_key

def select_model() -> Tuple[str, str, int, int]:
    """Interactive model selection"""
    print(f"\n{colored('📊 Available Models:', Colors.CYAN)}")
    for key, model_info in GROQ_MODELS.items():
        print(f"  {key}. {model_info['display']}")
        print(f"     Max RPM: {model_info['max_rpm']} | Max TPM: {model_info['max_tpm']}")
    
    choice = input(f"\n{colored('Select model (1 or 2): ', Colors.YELLOW)}")
    
    if choice not in GROQ_MODELS:
        print(f"{colored('❌ Invalid choice', Colors.RED)}")
        sys.exit(1)
    
    model_info = GROQ_MODELS[choice]
    return model_info["name"], choice, model_info["max_rpm"], model_info["max_tpm"]

def get_codebase_path() -> str:
    """Prompt for codebase path"""
    print(f"\n{colored('📁 Enter path to codebase:', Colors.CYAN)}")
    path = input("→ ").strip()
    
    if not Path(path).exists():
        print(f"{colored('❌ Path does not exist', Colors.RED)}")
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
    """Estimate total tokens for all files (1 token ≈ 4 chars)"""
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
    print(f"\n{colored('═' * 60, Colors.BOLD)}")
    print(f"{colored('📋 AUDIT CONFIRMATION PHASE', Colors.BOLD)}")
    print(f"{colored('═' * 60, Colors.BOLD)}\n")
    
    # Cap to Top 150 files
    top_files = files[:150] if len(files) > 150 else files
    
    if len(files) > 150:
        print(f"{colored(f'⚠️  Capping audit to Top 150 highest-risk files (from {len(files)} total)', Colors.YELLOW)}\n")
    
    # Group files by extension
    grouped = group_files_by_extension(top_files)
    
    # Sort by count (descending)
    sorted_groups = sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True)
    
    print(f"{colored('📁 Files by Extension (Top 150):', Colors.CYAN)}\n")
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
    
    print(f"{colored(f'📊 Token Estimate: ~{total_tokens:,} tokens', Colors.CYAN)}")
    print(f"{colored(f'📈 Total Files: {total_files}', Colors.CYAN)}")
    print(f"{colored(f'🎯 Highest Risk Score: {max_risk_score}', Colors.RED)}")
    print(f"{colored(f'🤖 Model: {model_name}', Colors.CYAN)}\n")
    
    # Gatekeeper prompt
    print(f"{colored('⚠️  Ready to send', Colors.YELLOW)} {colored(f'{total_files}', Colors.BOLD)} {colored('files (~', Colors.YELLOW)}{colored(f'{total_tokens:,}', Colors.BOLD)} {colored('tokens) to Groq.', Colors.YELLOW)}")
    
    response = input(f"\n{colored('Proceed with audit? [y/N]: ', Colors.YELLOW)}")
    
    if response.lower() == 'y':
        print(f"\n{colored('✅ Audit confirmed. Starting surgical strike...', Colors.GREEN)}\n")
        return True, top_files
    else:
        print(f"\n{colored('❌ Audit cancelled by user.', Colors.RED)}")
        return False, []

def print_results(client: GroqAuditClient, results: List[Dict]):
    """Print formatted results"""
    print(f"\n{colored('═' * 60, Colors.BOLD)}")
    print(f"{colored('📊 AUDIT RESULTS', Colors.BOLD)}")
    print(f"{colored('═' * 60, Colors.BOLD)}\n")
    
    safe_count = sum(1 for r in results if r.get("status") == "safe")
    vulnerable_count = sum(1 for r in results if r.get("status") == "vulnerable")
    error_count = sum(1 for r in results if r.get("status") == "error")
    skipped_count = sum(1 for r in results if r.get("status") == "skipped")
    
    print(f"{colored(f'✓ Safe: {safe_count}', Colors.GREEN)}")
    print(f"{colored(f'⚠ Vulnerable: {vulnerable_count}', Colors.YELLOW)}")
    print(f"{colored(f'⊘ Skipped (Layer 1): {skipped_count}', Colors.DIM)}")
    print(f"{colored(f'✗ Errors: {error_count}', Colors.RED)}")
    print(f"{colored(f'📈 Total Tokens Used: {client.total_tokens:,}', Colors.CYAN)}\n")
    
    if client.vulnerabilities_found:
        print(f"{colored('🔴 VULNERABILITIES FOUND:', Colors.RED)}\n")
        for vuln in client.vulnerabilities_found:
            file_path = vuln["file"]
            summary = vuln.get("summary", vuln["finding"][:80])
            finding = vuln["finding"]
            
            print(f"{colored(f'📄 {file_path}', Colors.YELLOW)}")
            print(f"{colored(f'   ⚠️  {summary}', Colors.RED)}")
            print()
    
    # Latency stats
    latencies = [r.get("latency", 0) for r in results if r.get("latency") and r.get("status") != "skipped"]
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        print(f"{colored(f'⏱️  Avg Latency: {avg_latency:.2f}s | Max: {max_latency:.2f}s', Colors.DIM)}")
    
    # Ghost-to-Star Banner
    print(f"\n{colored('═' * 60, Colors.BOLD)}")
    print(f"{colored('⭐ Like the results? Support the project on GitHub:', Colors.YELLOW)}")
    print(f"{colored('https://github.com/EthanBaron/Trepan', Colors.YELLOW)}")
    print(f"{colored('═' * 60, Colors.BOLD)}\n")

# ─── Main ───────────────────────────────────────────────────────────────────

async def main():
    print_header()
    
    # ── TASK 0: INTERACTIVE EXECUTION MODE (MANDATORY) ──────────────────────
    print(f"\n{colored('🧪 TREPAN SELF-VALIDATION SYSTEM', Colors.BOLD)}")
    print(f"{colored('═' * 60, Colors.BOLD)}\n")
    
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
            print(f"\n{colored('🚨 CALIBRATION ERROR: Auditor is unreliable. Aborting scan.', Colors.RED)}")
            sys.exit(1)
        
        print(f"{colored('✅ All sanity tests passed! System is calibrated.', Colors.GREEN)}\n")
    
    elif mode_choice != "2":
        print(f"{colored('❌ Invalid choice. Exiting.', Colors.RED)}")
        sys.exit(1)
    
    # ── CONTINUE TO FULL AUDIT ──────────────────────────────────────────────
    
    # Get configuration
    api_key = get_api_key()
    model_name, model_choice, max_rpm, max_tpm = select_model()
    codebase_path = get_codebase_path()
    
    # File extensions to scan
    extensions = ['.py', '.js', '.ts', '.java', '.go', '.rb', '.php', '.cs']
    
    # Initialize components
    rate_limiter = TokenBucket(max_rpm, max_tpm)
    scanner = CodebaseScanner(codebase_path, extensions, max_size_kb=500)
    client = GroqAuditClient(api_key, model_name, rate_limiter)
    
    # Scan codebase (Layer1PreScreener applied during scan, files sorted by risk score)
    files = scanner.scan()
    if not files:
        print(f"{colored('❌ No auditable files found after filtering', Colors.RED)}")
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
    print_results(client, results)
    
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
    
    print(f"{colored('⏱️  Audit Duration: ', Colors.CYAN)}{colored(time_str, Colors.BOLD)}")
    
    print(f"\n{colored('✅ Stress test complete!', Colors.GREEN)}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{colored('⚠️  Audit interrupted by user', Colors.YELLOW)}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{colored(f'❌ Error: {str(e)}', Colors.RED)}")
        sys.exit(1)
