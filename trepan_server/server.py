#!/usr/bin/env python3
"""
🛡️ Trepan Gatekeeper — FastAPI Server
POST /evaluate  → drift evaluation using llama3.1:8b
GET  /health    → status + model loaded flag
"""

# Force UTF-8 output on Windows to prevent charmap codec crashes with emoji characters
import sys, io
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import os
import re
import time
import json
import hashlib
import difflib
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Add Rule Sanctuary path detection function
def is_trepan_path(file_path: str) -> bool:
    """
    Robust path analysis to detect .trepan/ folder paths.
    Uses proper path parsing with os.path.normpath() for cross-platform compatibility.

    Args:
        file_path: The file path to analyze (can be relative or absolute)

    Returns:
        bool: True if the path is within a .trepan/ folder, False otherwise
    """
    if not file_path:
        return False

    # Normalize the path for cross-platform compatibility
    normalized_path = os.path.normpath(file_path)

    # Split the path into components
    path_parts = normalized_path.split(os.path.sep)

    # Check if any part of the path is ".trepan"
    return ".trepan" in path_parts

# Handle both relative and absolute imports for flexibility
try:
    from .prompt_builder import build_prompt, build_meta_gate_prompt, STRUCTURAL_INTEGRITY_SYSTEM, METAGATE_AUDIT_SYSTEM
    from .response_parser import guillotine_parser
    from .model_loader import get_model, generate
except ImportError:
    # Fallback for when running directly (not as a package)
    from prompt_builder import build_prompt, build_meta_gate_prompt, STRUCTURAL_INTEGRITY_SYSTEM, METAGATE_AUDIT_SYSTEM
    from response_parser import guillotine_parser
    from model_loader import get_model, generate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("trepan.server")

# ─── Cross-Platform Path Resolver ─────────────────────────────────────────────

def get_root_dir() -> str:
    """
    Returns the absolute path to the project root directory.
    Dynamically resolved relative to this file so it works across Windows, macOS, Linux, and WSL 
    without any hardcoded paths.
    """
    # This file is in trepan_server/server.py
    # The project root is one level up.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── Diagnostic Trace Logger (ssart_trace_sync.log) ─────────────────────────
_trace_sync_logger = logging.getLogger("trepan.trace_sync")
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

## Mandatory Security Baseline
- NO hardcoded secrets, API keys, or passwords
- NO `eval()` or `exec()` with user input
- NO `os.system()` or `subprocess` with `shell=True`
- ALL file paths must use `os.path.realpath()` + `startswith()` validation
- ALL SQL queries must use parameterized statements
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

## Mandatory Security Baseline
- NO hardcoded secrets, API keys, or passwords
- NO `eval()` or `exec()` with user input
- NO `os.system()` or `subprocess` with `shell=True`
- ALL file paths must use `os.path.realpath()` + `startswith()` validation
- ALL SQL queries must use parameterized statements
- Input validation at layer boundaries
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

## Mandatory Code Security
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

## Rule 100: DOM_INTEGRITY_PROTECTION
- Forbidden use of innerHTML, outerHTML, or document.write.
- Reasoning: These are primary XSS vectors.
- Action: Use textContent or innerText instead.
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
    vault_dir = os.path.join(root_dir, ".trepan", "trepan_vault")
    
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
    """Check if the Vault matches the .trepan.lock signature."""
    root_dir = project_path if project_path else get_root_dir()
    lock_file = os.path.join(root_dir, ".trepan", ".trepan.lock")
    
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
    Sign the vault by saving its hash to .trepan.lock in JSON format.
    
    Args:
        root_dir: Optional. Absolute path to project root. Defaults to get_root_dir().
    """
    if not root_dir:
        root_dir = get_root_dir()
    lock_file = os.path.join(root_dir, ".trepan", ".trepan.lock")
    
    file_hash = calculate_vault_hash(root_dir)
    
    lock_payload = {
        "signature": file_hash,
        "last_updated": time.time(),
        "status": "SECURE",
        "warning": "DO NOT EDIT. TAMPERING WILL BREAK TREPAN SYNC."
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
    vault_dir = os.path.join(root_dir, ".trepan", "trepan_vault")
    
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
    
    # 2.2 Live folder target (e.g. .trepan/system_rules.md)
    trepan_dir = os.path.join(root_dir, ".trepan")
    live_file_path = os.path.join(trepan_dir, filename)
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


def create_default_pillars(trepan_dir: str):
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

## Trepan System Rules

1. YOUR ARE NOT ALLOWED TO TOUCH trepan_vault NOR .trepan.lock
2. The AI must create a Walkthrough file to document its work and intent
3. Strict Contextual Synchronization: Every architectural change must align with the Project Context (README)

**Note**: Use `Trepan: Initialize Project` command to generate mode-specific rules (Solo-Indie, Clean-Layers, or Secure-Stateless).
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
- Trepan initialized
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

Document problems you encounter and their resolutions. Trepan can learn from these!

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
        filepath = os.path.join(trepan_dir, filename)
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
        trepan_dir = os.path.join(root_dir, ".trepan")
        
        # Action 2: Put trepan_vault INSIDE the .trepan folder
        vault_dir = os.path.join(trepan_dir, "trepan_vault")
        
        print(f"Target Root: {root_dir}")
        print(f"Source .trepan: {trepan_dir} (Exists? {os.path.exists(trepan_dir)})")
        print(f"Target Vault: {vault_dir}")
        
        os.makedirs(vault_dir, exist_ok=True)
        print(f"os.makedirs called. Vault exists on disk? {os.path.exists(vault_dir)}")
        
        # NEW: Create default pillar files if they don't exist
        create_default_pillars(trepan_dir)
        
        # Action: Initialize the Walkthrough Audit Ledger
        initialize_audit_ledger(trepan_dir)
        
        # Action: Ensure Default Rules exist in the source system_rules.md
        sys_rules_src = os.path.join(trepan_dir, "system_rules.md")
        if os.path.exists(sys_rules_src):
            print("\n[RULE GUARDIAN] Scanning system_rules.md for mandatory defaults...")
            with open(sys_rules_src, "r", encoding="utf-8") as f:
                raw = f.read()
            # Normalize line endings so all checks work on LF-only content
            sys_content = raw.replace("\r\n", "\n").replace("\r", "\n")

            # FIX: Never inject defaults if the section header already exists.
            # This prevents the header from being appended multiple times when
            # rule check-strings no longer match due to user edits.
            if "## Trepan Mandatory Defaults" in sys_content:
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
                    ("YOUR ARE NOT ALLOWED TO TOUCH trepan_vault NOR .trepan.lock", "YOUR ARE NOT ALLOWED TO TOUCH trepan_vault NOR .trepan.lock"),
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
                        f.write("\n\n## Trepan Mandatory Defaults\n")
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
        lock_file = os.path.join(trepan_dir, ".trepan.lock")
        is_first_init = not os.path.exists(lock_file)
        
        if not is_first_init:
            missing_vault_files = []
            for pillar in PILLARS:
                v_path = os.path.join(vault_dir, pillar)
                if not os.path.exists(v_path) and os.path.exists(os.path.join(trepan_dir, pillar)):
                    missing_vault_files.append(pillar)
            if missing_vault_files:
                print(f"🚨 [STRICT CHECK] Vault folder exists but is missing: {missing_vault_files}")
                print("🔄 Triggering FORCE_REBUILD of the Vault...")
                is_first_init = True
                
        print(f"\n[VAULT LOCK] Lock file path : {lock_file}")
        print(f"[VAULT LOCK] Lock exists     : {os.path.exists(lock_file)}")
        print(f"[VAULT LOCK] Mode            : {'FIRST INIT / REBUILD - seeding from .trepan/' if is_first_init else 'RESTART - loading frozen snapshot'}")
        
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
            src = os.path.join(trepan_dir, pillar)
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
                    print(f"  [VAULT] Seeded {pillar} from .trepan/ (Atomic Write)")
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
                _src = os.path.join(trepan_dir, p)
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
            print("  -> Live .trepan/ files are NOT copied to vault. Only ACCEPT verdicts update the vault.")
        
        print("="*50 + "\n")
        
        logger.info(f"Shadow Vault initialized at {vault_dir} and loaded into memory.")
    except Exception as e:
        print(f"\nCRITICAL ERROR IN init_vault: {e}")
        import traceback
        traceback.print_exc()
        print("="*50 + "\n")
        logger.error(f"Failed to init shadow vault: {e}")

def find_walkthrough_file(trepan_dir: str) -> str:
    """
    Looks for any file starting with 'walkthrough' in the .trepan configuration directory,
    ensuring we support generic extensions (e.g., .md, .txt) mapped by different LLMs.
    Returns path to the found file, or defaults to Walkthrough.md if none exists.
    """
    if os.path.exists(trepan_dir):
        for fname in os.listdir(trepan_dir):
            if fname.lower().startswith("walkthrough"):
                return os.path.join(trepan_dir, fname)
    return os.path.join(trepan_dir, "Walkthrough.md")

def initialize_audit_ledger(trepan_dir: str):
    """
    Creates Walkthrough.md (The Live Comparison Ledger) if it doesn't exist.
    It serves as a tutorial at the start, establishing the absolute 'Perfect' baseline.
    """
    ledger_path = find_walkthrough_file(trepan_dir)
    if not os.path.exists(ledger_path):
        ledger_name = os.path.basename(ledger_path)
        print(f"\n[LEDGER] Initializing Trepan Audit Ledger ({ledger_name})...")
        template = (
            "# Trepan Architectural Audit & Tutorial\n\n"
            "Welcome to Trepan! This file serves as your Live Comparison Ledger.\n"
            "This file will now be updated after every execution. Compare the AI `[THOUGHT]` "
            "section below to the Absolute Solution to catch hallucinations or context drift.\n\n"
            "## Reference Architecture (The Ground Truth)\n\n"
            "This section defines the 'Perfect' baseline for Trepan's reasoning. "
            "All future AI thoughts will be compared against this reference to detect drift.\n\n"
            "### Core Principles\n"
            "1. **Contextual Alignment**: Every change must align with the project's README and golden_state.md\n"
            "2. **Rule Compliance**: No violations of system_rules.md are permitted\n"
            "3. **Architectural Consistency**: Changes must maintain the established architecture\n"
            "4. **Security First**: No hardcoded secrets, unsafe eval(), or shell injection risks\n\n"
            "### Perfect Execution Example\n"
            "When Trepan is thinking clearly, a perfect execution looks like this:\n"
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
    Auto-generates the Trepan README.md in the .trepan folder if it doesn't exist.
    This serves as the "README of Truth" for users.
    """
    trepan_dir = os.path.join(project_path, ".trepan")
    readme_path = os.path.join(trepan_dir, "README.md")
    root_readme_path = os.path.join(project_path, "README.md")
    # FORCE OVERWRITE check for 6 pillars
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            old_readme = f.read()
        if "The Six Pillars" not in old_readme:
            print(f"[README GUARDIAN] Upgrading Trepan README.md to 6-Pillar Architecture...")
            os.remove(readme_path) # Force re-creation below

    if not os.path.exists(readme_path):
        print(f"\n[README GUARDIAN] Initializing Trepan README.md...")
        readme_content = """# Trepan: The Architectural Seatbelt 🛡️

**100% Local. Zero Cloud Leakage. Absolute Intent Verification.**

Most AI tools are "Yes-Men"—they help you write spaghetti code faster. Trepan is the "No-Man." It is a local-first architectural linter designed to stop "Architecture Drift" before it hits your codebase. Built for developers who value integrity over just "vibes."

---

## 🔒 The 100% Local Promise

Your code is your most valuable asset. Why send it to the cloud?

- **Zero Cloud Leakage**: Trepan runs entirely on your hardware. No AWS, no OpenAI, no metadata sent to third parties.
- **Privacy-First**: Powered by a local Llama 3.1 (8B) model via Ollama.
- **War-Room Ready**: Designed to work offline. Your security isn't dependent on an internet connection or a corporate API's uptime.

---

## 🏎️ The Architectural Seatbelt

Trepan doesn't just check syntax; it enforces **Intent**.

### The Guillotine Parser
A production-hardened filter (7/7 stress tests passed) that strips away AI hallucinations and "yap," leaving only a raw ACCEPT or REJECT verdict.

### Closed-Loop Audit
Every AI decision is logged in `Walkthrough.md`. Trepan "looks back" at your Reference Architecture to verify the AI isn't lying about its reasoning.

### Intent-Diff Verification
Before you commit, use the Side-by-Side Review. Compare the AI's explained "Thought" against the actual code diff to ensure the "Why" matches the "What."

---

## 🛠️ Technical Specifications

To ensure Trepan's "Seatbelt" engages correctly, verify your local environment matches these production-tested specs.

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
- **Communication**: Trepan Server defaults to `localhost:8000`. Ensure this port is not blocked by local firewalls.

### 4. Filesystem Structure
Upon initialization, Trepan manages the following in your project root:
- `.trepan/trepan_vault/` - Holds your cryptographically-signed Architectural Pillar snapshots
- `.trepan/Walkthrough.md` - The live Audit Ledger and Reference Architecture
- `.trepan/.trepan.lock` - SHA-256 signature of the vault (DO NOT EDIT)

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10 or 3.11
- Ollama with llama3.1 model: `ollama pull llama3.1:8b`
- VS Code 1.85.0+

### Installation

1. **Start the Trepan Server**
   ```bash
   cd trepan_server
   python -m uvicorn server:app --reload
   ```
   Wait for the "✅ Trepan_Model_V2 ready" message.

2. **Install VS Code Extension**
   - Open VS Code
   - Install the Trepan Gatekeeper extension from the marketplace
   - Or install from source: `cd extension && npm install && code --install-extension .`

3. **Initialize Your Project**
   - The `.trepan` folder auto-creates on first server start
   - Edit `.trepan/system_rules.md` to define your architectural rules
   - Edit `.trepan/golden_state.md` to define your project architecture

4. **Test the Seatbelt**
   - Make a code change in your project
   - Save the file
   - Watch Trepan evaluate it in real-time
   - Status bar shows: `🛡️ Trepan ✅`

---

## 🛠️ The Developer's Audit

When Trepan rejects a change, don't just take its word for it:

1. **Open the Side-by-Side Review**
   - Press `Ctrl+Shift+P` (Windows) or `Cmd+Shift+P` (Mac)
   - Run: "Trepan: Review Changes vs. Walkthrough"

2. **Compare**
   - Code on the Left | Audit Trail on the Right
   - See exactly which Pillar was violated
   - Understand why the "Guillotine" dropped

3. **Verify**
   - Check if the AI's reasoning matches reality
   - Look for hallucinations or context drift
   - Override if the AI is wrong (you're in control)

---

## 📋 The Six Pillars of the Trepan Vault

Trepan enforces architectural consistency and dynamic learning through six core documents in `.trepan/`:

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
Trepan protects your architectural rules with a cryptographic vault in `.trepan/trepan_vault/`. 
- **Meta-Gate Validation**: Changes to your rules (`.trepan/*.md`) are reviewed by a specialized Meta-Gate AI to ensure intent is preserved.
- **SHA-256 Locking**: The entire vault is signed in `.trepan.lock` to prevent unauthorized out-of-band tampering.

---

## 🎓 Philosophy
AI should be a skeptical partner, not a yes-man. Trepan optimizes for **architectural integrity**, ensuring your project's soul isn't lost in the "vibe" of rapid AI iteration.

**Your code stays on your machine. Always.**

| `Trepan: Show Server Status` | Check if server is online |
| `Trepan: Toggle Airbag On/Off` | Enable/disable save blocking |
| `Trepan: Open Trepan Ledger` | View Walkthrough.md |
| `Trepan: Review Changes vs. Walkthrough` | Side-by-side code + audit view |
| `Ask Trepan` | Highlight code and ask for evaluation |

---

## ⚙️ Configuration

Edit VS Code settings (`settings.json`):

```json
{
  "trepan.serverUrl": "http://127.0.0.1:8000",
  "trepan.enabled": true,
  "trepan.timeoutMs": 30000,
  "trepan.excludePatterns": [
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
- Reload VS Code window: `Ctrl+Shift+P` -> "Developer: Reload Window"
- Check firewall isn't blocking localhost:8000

### Saves always blocked
- Check `.trepan/system_rules.md` for overly strict rules
- Review `Walkthrough.md` to see why saves are rejected
- Temporarily disable: `Ctrl+Shift+P` -> "Trepan: Toggle Airbag On/Off"

### Vault Compromised Error
- This means `.trepan/trepan_vault/` files or `.trepan.lock` were manually edited
- To fix: Review your pillar files, then run the "Re-sign Vault" command from the Trepan sidebar
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

Trepan is built on the principle that **AI should be a skeptical partner, not a yes-man**. 

Most AI coding assistants optimize for speed and convenience. Trepan optimizes for **architectural integrity**. It's designed for:

- **Security-conscious developers** who can't afford to leak code to the cloud
- **Solo developers** who need a second pair of eyes on architectural decisions
- **Teams** who want to enforce consistent patterns across the codebase
- **High-stakes environments** where architectural drift has real consequences

---

## 🚨 Beta Status

Trepan is currently in a **14-day Private Beta**. As a solo developer building in a high-stakes environment, I value your technical feedback above all else.

If Trepan catches a drift for you, consider:
- Starring the repo
- Reporting issues on GitHub
- Sharing your use case

---

## 📄 License

[Your License Here]

---

## 🛡️ Built with Integrity

Trepan was built by a developer who needed it. No VC funding. No cloud dependencies. No compromises on privacy.

**Your code stays on your machine. Always.**
"""

    # Only manage .trepan/README.md — root README is the developer's responsibility
    if not os.path.exists(readme_path):
        print(f"\n[README GUARDIAN] Initializing Trepan README.md at {readme_path}...")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)
        print(f"[README GUARDIAN] .trepan/README.md created successfully.")
    else:
        with open(readme_path, "r", encoding="utf-8") as f:
            if "The Six Pillars" not in f.read():
                print(f"[README GUARDIAN] Upgrading .trepan/README.md to 6-Pillar Architecture...")
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(readme_content)
                print(f"[README GUARDIAN] .trepan/README.md upgraded.")


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
        trepan_dir = os.path.join(root_dir, ".trepan")
        ledger_path = find_walkthrough_file(trepan_dir)
        
        # Ensure file exists
        if not os.path.exists(ledger_path):
            logger.warning(f"Walkthrough.md not found at {ledger_path}, creating it...")
            initialize_audit_ledger(trepan_dir)
        
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
    audit_prompt = f"""SYSTEM: You are the TREPAN ARCHITECT. 
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
    print("🕵️ TREPAN VALIDATION ENGINE THOUGHTS:")
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
    trepan_dir = os.path.join(root_dir, ".trepan")
    ledger_path = find_walkthrough_file(trepan_dir)
    
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
    audit_prompt = f"""SYSTEM: You are the TREPAN AUDITOR.
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
    print("🔍 TREPAN CLOSED-LOOP AUDIT:")
    print(raw)
    print("="*40 + "\n")
    
    result = guillotine_parser(raw)
    
    if result['verdict'] == "REJECT":
        logger.warning(f"Closed-loop audit detected drift: {result['reasoning'][:100]}")
    
    return result

def initialize_project_with_template(mode: str, project_path: str) -> dict:
    """
    Initializes a Trepan project with a golden template.
    
    Steps:
    1. Create .trepan directory structure
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
    trepan_dir = os.path.join(project_path, ".trepan")
    
    try:
        # Step 1: Create directory structure
        os.makedirs(trepan_dir, exist_ok=True)
        vault_dir = os.path.join(trepan_dir, "trepan_vault")
        os.makedirs(vault_dir, exist_ok=True)
        
        print(f"\n[GOLDEN TEMPLATE] Initializing project with mode: {template['name']}")
        
        # Step 2: Write system_rules.md
        rules_path = os.path.join(trepan_dir, "system_rules.md")
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
            pillar_path = os.path.join(trepan_dir, filename)
            if not os.path.exists(pillar_path): # Prevent overwriting if file exists
                with open(pillar_path, "w", encoding="utf-8") as f:
                    f.write(content)
        
        print(f"[GOLDEN TEMPLATE] Created all pillar files")

        # Step 4: Initialize Walkthrough.md and README.md
        initialize_audit_ledger(trepan_dir)
        initialize_project_readme(project_path)
        
        # Step 5: Generate golden_state.md using LLM (STAY ROBUST)
        print(f"[GOLDEN TEMPLATE] Generating Perfect Execution example using Llama 3.1 8B...")
        
        golden_example = ""
        try:
            golden_prompt = template['llm_prompt']
            golden_example = generate(golden_prompt)
        except Exception as llm_err:
            logger.warning(f"LLM generation failed for golden_state.md: {llm_err}")
            golden_example = f"\n> [!WARNING]\n> **LLM OFFLINE/BUSY:** Perfect Execution example generation failed.\n> Trepan will learn from your first few accepted code changes instead.\n\n_Reason: {str(llm_err)}_"

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
        
        golden_state_path = os.path.join(trepan_dir, "golden_state.md")
        with open(golden_state_path, "w", encoding="utf-8") as f:
            f.write(golden_state_content)
        print(f"[GOLDEN TEMPLATE] Created golden_state.md")
        
        # Step 6: Create vault snapshots and lock
        for pillar in PILLARS:
            src = os.path.join(trepan_dir, pillar)
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
    trepan_dir = os.path.join(project_path, ".trepan")
    pending_path = os.path.join(trepan_dir, "pending_tasks.md")
    done_path = os.path.join(trepan_dir, "done_tasks.md")
    history_path = os.path.join(trepan_dir, "history_phases.md")
    
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
        vault_dir = os.path.join(trepan_dir, "trepan_vault")
        for filename in ["pending_tasks.md", "done_tasks.md", "history_phases.md"]:
            src = os.path.join(trepan_dir, filename)
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
    trepan_dir = os.path.join(project_path, ".trepan")
    problems_path = os.path.join(trepan_dir, "problems_and_resolutions.md")
    golden_path = os.path.join(trepan_dir, "golden_state.md")
    rules_path = os.path.join(trepan_dir, "system_rules.md")
    history_path = os.path.join(trepan_dir, "history_phases.md")
    
    try:
        if not os.path.exists(problems_path):
            return {"status": "error", "message": "problems_and_resolutions.md not found"}
        
        with open(problems_path, "r", encoding="utf-8") as f:
            problems_content = f.read()
        
        # EVOLUTIONARY LOGIC GATE: Analyze problems with prioritization hierarchy
        analysis_prompt = f"""SYSTEM: You are the TREPAN EVOLUTIONARY ANALYZER.
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
        print("🧠 TREPAN EVOLUTIONARY MEMORY ANALYSIS:")
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
        vault_dir = os.path.join(trepan_dir, "trepan_vault")
        for filename in ["golden_state.md", "system_rules.md", "history_phases.md"]:
            src = os.path.join(trepan_dir, filename)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load the model during server startup with comprehensive error handling."""
    global _model_ready
    logger.info("🔄 Starting Trepan Gatekeeper server…")
    
    # EMERGENCY FIX 1: Wrap init_vault in try/except with full traceback
    try:
        init_vault()
        logger.info("✅ Vault initialized successfully")
    except Exception as vault_error:
        logger.error(f"❌ CRITICAL: Vault initialization failed: {vault_error}")
        import traceback
        logger.error("Full traceback:")
        logger.error(traceback.format_exc())
        logger.warning("⚠️  Server will start but vault operations may fail")
    
    # INITIALIZE NATIVE INFERENCE ENGINE: Load Trepan_Model_V2 into VRAM
    try:
        logger.info(f"🔍 Loading Native Trepan Model into VRAM...")
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
    logger.info("🛑 Trepan server shutting down")


# ─── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Trepan Gatekeeper",
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
    golden_state:             str = Field("", description="Contents of .trepan/golden_state.md")
    done_tasks:               str = Field("", description="Contents of .trepan/done_tasks.md")
    pending_tasks:            str = Field("", description="Contents of .trepan/pending_tasks.md")
    history_phases:           str = Field("", description="Phase history (optional)")
    system_rules:             str = Field("", description="Contents of .trepan/system_rules.md")
    problems_and_resolutions: str = Field("", description="Contents of .trepan/problems_and_resolutions.md (optional)")

class EvaluateRequest(BaseModel):
    filename:      str = Field(..., description="Filename being saved")
    code_snippet:  str = Field(..., description="Content of the file")
    pillars:       EvaluatePillars = Field(default_factory=EvaluatePillars)
    project_path:  str = Field("",    description="Absolute path to the project root")

class EvaluatePillarRequest(BaseModel):
    filename:         str = Field(..., description="The name of the pillar, e.g. system_rules.md")
    incoming_content: str = Field(..., description="The content of the pillar that the user is trying to save")
    project_path:     str = Field("",  description="Optional: Absolute path to the project root (sent by extension)")

class VerifyIntentRequest(BaseModel):
    ai_explanation: str = Field(..., description="The AI's generated walkthrough/explanation of its work.")

class InitializeProjectRequest(BaseModel):
    mode: str = Field(..., description="The golden template mode: solo-indie, clean-layers, or secure-stateless")
    project_path: str = Field(..., description="Absolute path to the project root directory")

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

class EvaluateResponse(BaseModel):
    action:        str   = Field(...,  description="ACCEPT, REJECT, or ERROR")
    drift_score:   float = Field(...,  description="0.0 (clean) – 1.0 (high drift)")
    reasoning:     str   = Field(...,  description="Cleaned [THOUGHT] reasoning text")
    vault_updated: bool  = Field(False, description="True if the vault snapshot was updated")
    vault_file:    str   = Field("",    description="Which vault file was updated (on ACCEPT)")
    # Structured violation details for sidebar display
    filename:      str   = Field("",    description="File that was audited")
    violations:    List[ViolationDetail] = Field(default_factory=list, description="Parsed violation details")


class HealthResponse(BaseModel):
    status:       str  = "ok"
    model_loaded: bool = False
    version:      str  = "2.0.0"


# ─── Routes ─────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Status"])
async def health(request: Request):
    """Quick liveness + readiness check for the IDE extension with detailed logging."""
    # TRANSPARENCY FIX: Log every health check request with client info
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    print(f"HEALTH CHECK REQUEST:")
    print(f"   Client IP: {client_ip}")
    print(f"   User-Agent: {user_agent}")
    print(f"   Model Ready: {_model_ready}")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    
    logger.info(f"Health check from {client_ip} - Model ready: {_model_ready}")
    
    response = HealthResponse(status="ok", model_loaded=_model_ready)
    print(f"   Response: {response.dict()}")
    print("=" * 50)
    
    return response


@app.post("/evaluate", response_model=EvaluateResponse, tags=["Gatekeeper"])
async def evaluate(req: EvaluateRequest):
    """
    Evaluate a user prompt against the 5 workspace pillars.

    Returns ACCEPT (drift_score < 0.40) or REJECT (drift_score >= 0.40).
    """
    # ── LOG SIGNAL ──
    # Extra diagnostic log as requested by user
    cmd_preview = req.code_snippet[:100].replace('\n', ' ')
    print(f"\n--- AUDIT REQUEST RECEIVED: {req.filename} ({cmd_preview}) ---")

    # HARDWARE CHECK: Log GPU status but never block the audit
    gpu_ok, gpu_msg = verify_gpu_loading()
    if not gpu_ok:
        logger.warning(f"GPU check: {gpu_msg} — continuing audit anyway")
    else:
        logger.info(f"GPU check: {gpu_msg}")

    if not is_trepan_path(req.filename):
        # ── DYNAMIC RULE-AWARE SCANNER (Zero-Baseline Upgrade) ──
        # Extract keywords directly from system_rules.md
        system_rules = req.pillars.system_rules or VAULT_STATE.get("system_rules.md", "")
        
        # Simple extraction: find words in backticks or common security functions
        # This allows the scanner to evolve as rules change.
        dynamic_keywords = set(re.findall(r'`([^`]+)`', system_rules))
        
        # Add fundamental baseline keywords if not present
        baseline_defaults = {"eval", "exec", "innerHTML", "os.system", "subprocess", "os.popen", "pickle.load", "marshal.load"}
        forbidden_keywords = list(dynamic_keywords.union(baseline_defaults))
        
        code_lower = req.code_snippet.lower()
        line_count = len(req.code_snippet.splitlines())
        
        has_forbidden = any(kw.lower() in code_lower for kw in forbidden_keywords)
        
        # SMART TRIGGER: Only bypass if ZERO matches AND short code.
        # If any keyword matches, it MUST go to Ollama for context analysis.
        if line_count < 15 and not has_forbidden:
            logger.info(f"✨ Zero-Baseline: Code is clean/simple ({line_count} lines). Bypassing LLM.")
            return EvaluateResponse(
                action="ACCEPT",
                drift_score=0.0,
                reasoning="Trepan: Code verified clean via Dynamic Zero-Baseline (No prohibited keywords from system_rules.md detected).",
                violations=[],
                filename=req.filename
            )
        
    if not _model_ready:
        raise HTTPException(
            status_code=503,
            detail="Trepan model is still loading. Retry in a few seconds."
        )

    root_dir = get_root_dir()
    


    # Determine file extension from filename
    file_extension = os.path.splitext(req.filename)[1]
    
    # GROUNDING: Prepend line numbers to the code snippet
    grounded_code = prepend_line_numbers(req.code_snippet)
    
    prompt = build_prompt(
        system_rules=req.pillars.system_rules,
        user_command=grounded_code,
        file_extension=file_extension,
    )

    # Run inference natively — offloaded to thread pool so the async event loop
    # is NOT blocked during GPU inference. Without this, health checks queue up
    # and the VS Code client disconnects before inference finishes (silent fail).
    # STRUCTURAL_INTEGRITY_SYSTEM is passed as the system prompt so it occupies
    # the Llama 3 <|system|> role instead of eating user token budget.
    t0 = time.perf_counter()
    try:
        raw = await asyncio.to_thread(generate, prompt, STRUCTURAL_INTEGRITY_SYSTEM)

        print("\n" + "="*40)
        print("🧠 TREPAN RAW THOUGHTS:")
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
    result = guillotine_parser(raw, system_rules)
    
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

    logger.info(
        f"file={req.filename}"
    )

    # ── DEBUG LOGGING: Track data transmission ──
    logger.info(
        f"[TREPAN DEBUG] Returning response: action={result['verdict']}, "
        f"drift_score={result['score']:.2f}, raw_output_length={len(result['reasoning'])}"
    )

    # DIAGNOSTIC: expose parser violations and raw output for debugging
    logger.info(f"[VIOLATION DEBUG] violations={result['violations']}")
    logger.info(f"[RAW OUTPUT DEBUG] raw_output={result['raw_output']!r}")
    return EvaluateResponse(
        action=result['verdict'],
        drift_score=result['score'],
        reasoning=result['reasoning'],
        violations=result['violations'],
        filename=req.filename
    )

# ─── Vault Recovery & Resigning Endpoint ───────────────────────────────────

@app.post("/resign_vault", response_model=ResignResponse, tags=["Security"])
async def resign_vault():
    """Action 1 & 2: Recovery mechanism if the Vault is tampered with."""
    global VAULT_STATE
    root_dir = get_root_dir()  # Explicitly use hardcoded path for main vault
    trepan_dir = os.path.join(root_dir, ".trepan")
    vault_dir = os.path.join(trepan_dir, "trepan_vault")
    
    # Overwrite the vault files with Ground-Truth workspace files
    for pillar in PILLARS:
        src = os.path.join(trepan_dir, pillar)
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
    trepan_dir = os.path.join(root_dir, ".trepan")
    vault_dir = os.path.join(trepan_dir, "trepan_vault")
    
    os.makedirs(vault_dir, exist_ok=True)
    
    synced_files = []
    
    for pillar in PILLARS:
        live_path = os.path.join(trepan_dir, pillar)
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
    # Before every audit, sync the latest .md files from .trepan/ to vault
    # This ensures the AI judges against the ABSOLUTE LATEST architectural laws
    
    global VAULT_STATE
    root_dir = req.project_path if req.project_path else get_root_dir()
    trepan_dir = os.path.join(root_dir, ".trepan")
    vault_dir = os.path.join(trepan_dir, "trepan_vault")
    
    os.makedirs(vault_dir, exist_ok=True)
    
    pre_flight_synced = []
    for pillar in PILLARS:
        live_path = os.path.join(trepan_dir, pillar)
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
        raise HTTPException(status_code=503, detail="Trepan model is still loading.")
        
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
        raw = await asyncio.to_thread(generate, user_prompt, system_prompt=system_prompt)

        print("\n" + "="*40)
        print("🏛️ TREPAN META-GATE RAW THOUGHTS:")
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
            print(f"[VAULT SYNC] Complete ✅ — trepan_vault/{req.filename} is now the new baseline.")
            vault_updated = True
        except (PermissionError, OSError) as e:
            _trace_sync_logger.critical(f"VAULT SYNC FAILED for '{req.filename}' — {type(e).__name__}: errno={e.errno}, msg={e.strerror}")
            logger.error(f"Vault sync failed for {req.filename}: {e}")
            raise HTTPException(status_code=500, detail=f"Vault sync failed: {e.strerror} (errno={e.errno})")
    else:
        _trace_sync_logger.info(f"REJECT VERDICT — vault NOT updated for '{req.filename}' (score={result['score']})")

    # ── DEBUG LOGGING: Track data transmission ──
    logger.info(
        f"[TREPAN DEBUG] Returning response: action={result['verdict']}, "
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
        raise HTTPException(status_code=503, detail="Trepan model is still loading.")
        
    t0 = time.perf_counter()
    
    root_dir = get_root_dir()
    golden_rules_path = os.path.join(root_dir, ".trepan", "system_rules.md")
    
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
        raise HTTPException(status_code=503, detail="Trepan model is still loading.")
        
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
    Initialize a Trepan project with a golden template.
    
    Modes:
    - solo-indie: Simple, readable code for solo developers
    - clean-layers: Strict separation of concerns for long-term projects
    - secure-stateless: Maximum security with zero-trust architecture
    """
    if not _model_ready:
        raise HTTPException(status_code=503, detail="Trepan model is still loading.")
    
    logger.info(f"Initializing project at {req.project_path} with mode: {req.mode}")
    
    # Call the initialization function - let errors bubble up naturally
    result = initialize_project_with_template(req.mode, req.project_path)
    
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
        raise HTTPException(status_code=503, detail="Trepan model is still loading.")
    
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
    
    This is the core of the 5 Pillars Evolution Loop that allows Trepan to learn
    from past mistakes and successes.
    """
    if not _model_ready:
        raise HTTPException(status_code=503, detail="Trepan model is still loading.")
    
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
