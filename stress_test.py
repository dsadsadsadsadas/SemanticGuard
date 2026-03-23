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
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from collections import deque
import getpass

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
    def __init__(self, max_rpm: int, max_tpm: int):
        self.max_rpm = max_rpm
        self.max_tpm = max_tpm
        self.rpm_bucket = max_rpm
        self.tpm_bucket = max_tpm
        self.last_refill = time.time()
        self.token_history = deque(maxlen=60)  # Track tokens used in last 60 seconds
        
    def refill(self):
        """Refill buckets based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill
        
        # Refill RPM bucket (1 request per second max)
        self.rpm_bucket = min(self.max_rpm, self.rpm_bucket + (elapsed * self.max_rpm / 60))
        
        # Refill TPM bucket
        self.tpm_bucket = min(self.max_tpm, self.tpm_bucket + (elapsed * self.max_tpm / 60))
        
        self.last_refill = now
    
    def can_request(self, estimated_tokens: int = 1000) -> Tuple[bool, float]:
        """Check if we can make a request. Returns (can_request, wait_time)"""
        self.refill()
        
        if self.rpm_bucket >= 1 and self.tpm_bucket >= estimated_tokens:
            return True, 0.0
        
        # Calculate wait time
        rpm_wait = (1 - self.rpm_bucket) * (60 / self.max_rpm) if self.rpm_bucket < 1 else 0
        tpm_wait = (estimated_tokens - self.tpm_bucket) * (60 / self.max_tpm) if self.tpm_bucket < estimated_tokens else 0
        
        wait_time = max(rpm_wait, tpm_wait)
        return False, wait_time
    
    def consume(self, tokens_used: int):
        """Consume tokens from the bucket"""
        self.rpm_bucket -= 1
        self.tpm_bucket -= tokens_used
        self.token_history.append((time.time(), tokens_used))

# ─── File Scanner ──────────────────────────────────────────────────────────

class CodebaseScanner:
    def __init__(self, codebase_path: str, extensions: List[str], max_size_kb: int):
        self.codebase_path = Path(codebase_path)
        self.extensions = extensions
        self.max_size_kb = max_size_kb
        self.files = []
        
    def scan(self) -> List[Path]:
        """Recursively scan codebase for auditable files"""
        print(f"\n{colored('🔍 Scanning codebase...', Colors.CYAN)}")
        
        skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build'}
        
        for ext in self.extensions:
            pattern = f"**/*{ext}"
            for file_path in self.codebase_path.glob(pattern):
                # Skip excluded directories
                if any(skip_dir in file_path.parts for skip_dir in skip_dirs):
                    continue
                
                # Check file size
                size_kb = file_path.stat().st_size / 1024
                if size_kb > self.max_size_kb:
                    continue
                
                self.files.append(file_path)
        
        print(f"{colored(f'✓ Found {len(self.files)} auditable files', Colors.GREEN)}")
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
        return """You are an elite AppSec engineer with 15+ years of experience in security auditing.

You do NOT have specific architectural rules or project context.

Your job is to find:
1. Hardcoded secrets (API keys, passwords, tokens, credentials)
2. Injection flaws (SQL injection, command injection, template injection)
3. Incredibly bad anti-patterns (eval(), exec(), unsafe deserialization)
4. Critical security vulnerabilities (XXE, SSRF, path traversal, etc.)
5. Sensitive data exposure (logging passwords, PII in output, etc.)

CRITICAL RULES:
- Do NOT flag commented-out code as vulnerabilities
- Do NOT flag false positives on safe patterns
- Only flag REAL, EXPLOITABLE security issues
- If the code is safe or has no critical vulnerabilities, output exactly: SAFE
- If vulnerable, explain the flaw in 1-2 sentences with severity (CRITICAL/HIGH/MEDIUM)

Be concise. Be accurate. No false positives."""
    
    async def audit_file(self, file_path: Path) -> Dict:
        """Audit a single file"""
        try:
            # Read file
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                code = f.read()
            
            # Estimate tokens (rough: 1 token ≈ 4 chars)
            estimated_tokens = len(code) // 4 + 500
            
            # Wait for rate limit
            can_request, wait_time = self.rate_limiter.can_request(estimated_tokens)
            if not can_request:
                print(f"{colored(f'⏳ Rate limit: waiting {wait_time:.2f}s', Colors.YELLOW)}")
                await asyncio.sleep(wait_time)
            
            # Make API call
            start_time = time.time()
            response = requests.post(
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
                return {
                    "file": str(file_path),
                    "status": "error",
                    "error": response.text,
                    "latency": elapsed
                }
            
            data = response.json()
            tokens_used = data.get("usage", {}).get("total_tokens", estimated_tokens)
            result = data["choices"][0]["message"]["content"]
            
            # Consume tokens
            self.rate_limiter.consume(tokens_used)
            self.total_tokens += tokens_used
            self.files_scanned += 1
            
            # Parse result
            is_vulnerable = result.strip() != "SAFE"
            
            if is_vulnerable:
                self.vulnerabilities_found.append({
                    "file": str(file_path),
                    "finding": result
                })
            
            return {
                "file": str(file_path),
                "status": "vulnerable" if is_vulnerable else "safe",
                "finding": result if is_vulnerable else None,
                "tokens": tokens_used,
                "latency": elapsed
            }
        
        except Exception as e:
            return {
                "file": str(file_path),
                "status": "error",
                "error": str(e),
                "latency": 0
            }
    
    async def audit_codebase(self, files: List[Path], concurrency: int = 1):
        """Audit multiple files with concurrency control"""
        print(f"\n{colored('🚀 Starting audit...', Colors.CYAN)}")
        print(f"{colored(f'Model: {self.model} | Max RPM: {self.rate_limiter.max_rpm} | Max TPM: {self.rate_limiter.max_tpm}', Colors.DIM)}\n")
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def audit_with_semaphore(file_path):
            async with semaphore:
                return await self.audit_file(file_path)
        
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

def print_results(client: GroqAuditClient, results: List[Dict]):
    """Print formatted results"""
    print(f"\n{colored('═' * 60, Colors.BOLD)}")
    print(f"{colored('📊 AUDIT RESULTS', Colors.BOLD)}")
    print(f"{colored('═' * 60, Colors.BOLD)}\n")
    
    safe_count = sum(1 for r in results if r.get("status") == "safe")
    vulnerable_count = sum(1 for r in results if r.get("status") == "vulnerable")
    error_count = sum(1 for r in results if r.get("status") == "error")
    
    print(f"{colored(f'✓ Safe: {safe_count}', Colors.GREEN)}")
    print(f"{colored(f'⚠ Vulnerable: {vulnerable_count}', Colors.YELLOW)}")
    print(f"{colored(f'✗ Errors: {error_count}', Colors.RED)}")
    print(f"{colored(f'📈 Total Tokens Used: {client.total_tokens:,}', Colors.CYAN)}\n")
    
    if client.vulnerabilities_found:
        print(f"{colored('🔴 VULNERABILITIES FOUND:', Colors.RED)}\n")
        for vuln in client.vulnerabilities_found:
            print(f"{colored(f'File: {vuln[\"file\"]}', Colors.YELLOW)}")
            print(f"{colored(f'Finding: {vuln[\"finding\"]}', Colors.RED)}\n")
    
    # Latency stats
    latencies = [r.get("latency", 0) for r in results if r.get("latency")]
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        print(f"{colored(f'⏱️  Avg Latency: {avg_latency:.2f}s | Max: {max_latency:.2f}s', Colors.DIM)}")

# ─── Main ───────────────────────────────────────────────────────────────────

async def main():
    print_header()
    
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
    
    # Scan codebase
    files = scanner.scan()
    if not files:
        print(f"{colored('❌ No auditable files found', Colors.RED)}")
        sys.exit(1)
    
    # Run audit
    results = await client.audit_codebase(files, concurrency=1)
    
    # Print results
    print_results(client, results)
    
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
