#!/usr/bin/env python3
"""
🛡️ TREPAN 2.0 (Enterprise Edition)
A DevSecOps Context Enforcer with separated responsibilities:

PATH A: Silent Context Injection (Prevents Drift)
PATH B: Red Team Trigger (Only on Trouble Keywords)

Author: Project TREPAN
"""

import time
import os
import sys
import threading
import logging
import ast
import json
from datetime import datetime
from dotenv import load_dotenv
import pyperclip
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from groq import Groq

# --- CONFIGURATION ---
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CONTEXT_FILE = "GEMINI.md"  # The Architect's instruction file
MAX_CLIPBOARD_HISTORY = 5
SAFE_EXTENSIONS = {'.py', '.js', '.ts', '.html', '.css', '.java', '.cpp'}

# --- SETUP LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TREPAN")

if not GROQ_API_KEY:
    logger.error("❌ GROQ_API_KEY not found in .env")
    sys.exit(1)

client = Groq(api_key=GROQ_API_KEY)


# =============================================================================
# 1. PROJECT CACHE (The Memory)
# =============================================================================

class ProjectCache:
    def __init__(self):
        self.files = []
        self.scan_project()

    def scan_project(self):
        """Maps all relevant files in the directory."""
        self.files = []
        for root, _, filenames in os.walk("."):
            if "node_modules" in root or ".git" in root or "__pycache__" in root or "venv" in root:
                continue
            for f in filenames:
                if any(f.endswith(ext) for ext in SAFE_EXTENSIONS):
                    self.files.append(os.path.join(root, f))
        logger.info(f"📚 Cached {len(self.files)} project files")
    
    def find_relevant_file(self, query):
        """Heuristic to find a file based on a query keyword."""
        query = query.lower()
        
        # 1. Exact match (e.g. "login.py")
        for f in self.files:
            if os.path.basename(f).lower() in query:
                return f
        
        # 2. Keyword match (e.g. "login" -> "auth_login.py")
        keywords = query.split()
        for keyword in keywords:
            if len(keyword) < 3:
                continue
            for f in self.files:
                fname = os.path.basename(f).lower()
                if keyword in fname:
                    return f
        
        return None


# =============================================================================
# 2. AST ENGINE (Passive Defense - Local Security Scanning)
# =============================================================================

class SecurityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.issues = []

    def visit_Assign(self, node):
        """Detects hardcoded secrets in variables."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id.lower()
                if any(s in var_name for s in ['password', 'secret', 'key', 'token', 'auth', 'credential']):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        if len(node.value.value.strip()) > 0:
                            self.issues.append(f"Hardcoded Secret in '{target.id}' (line {node.lineno})")
        self.generic_visit(node)

    def visit_Call(self, node):
        """Detects unsafe logging of sensitive variables."""
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        
        unsafe_funcs = {'print', 'info', 'debug', 'warning', 'error', 'log'}
        if func_name in unsafe_funcs:
            for arg in node.args:
                if isinstance(arg, ast.Name):
                    if any(s in arg.id.lower() for s in ['password', 'secret', 'key', 'token']):
                        self.issues.append(f"Unsafe logging of '{arg.id}' in {func_name}() (line {node.lineno})")
        self.generic_visit(node)


def scan_file_security(filepath):
    """Runs AST analysis on a file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        visitor = SecurityVisitor()
        visitor.visit(tree)
        return visitor.issues
    except Exception:
        return []  # Ignore parse errors


# =============================================================================
# 3. RED TEAM MODULE (Active Attack - On Demand Only)
# =============================================================================

def execute_red_team_attack(target_content, filename):
    """Sends code to Groq for a hostile audit."""
    print(f"\n🚀 Launching Red Team attack on {filename}...")
    
    prompt = f"""You are a Hostile Red Team Security Expert.
TARGET: {filename}
CODE:
{target_content}

TASK:
Analyze this code for LOGICAL VULNERABILITIES (IDOR, Injection, Race Conditions, Hardcoded Secrets).
Ignore simple syntax errors. Be harsh but precise.

OUTPUT JSON ONLY:
{{
    "status": "SAFE" or "DANGER",
    "issue": "Brief description of the vulnerability (max 1 sentence)",
    "fix_instruction": "Precise instruction on how to fix it (max 2 sentences)"
}}
"""
    
    try:
        response = client.chat.completions.create(
            messages=[{"role": "system", "content": prompt}],
            model="llama-3.1-70b-versatile",
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        if isinstance(result, list):
            return result[0] if result else {"status": "SAFE", "issue": "No issues found"}
        return result
    except Exception as e:
        logger.error(f"Red Team Error: {e}")
        return {"status": "ERROR", "issue": str(e)}


def update_gemini_rules(audit_result, filename):
    """Writes the security constraint to GEMINI.md."""
    if audit_result.get("status") == "DANGER":
        rule = f"""
# 🛑 SECURITY INTERVENTION ({datetime.now().strftime('%H:%M:%S')})
# The Red Team detected a vulnerability in '{filename}': {audit_result['issue']}
# CONSTRAINT: You MUST implement the following fix: {audit_result['fix_instruction']}
"""
        try:
            with open(CONTEXT_FILE, "a", encoding="utf-8") as f:
                f.write(rule)
            print(f"✅ GEMINI.md updated with security constraint for {filename}.")
        except Exception as e:
            logger.error(f"Failed to update rules: {e}")


# =============================================================================
# 4. CLIPBOARD MONITOR (The Brain - Separated Responsibilities)
# =============================================================================

def monitor_clipboard(project_cache):
    """
    Smart Monitor with separated responsibilities:
    1. PATH A: ALWAYS updates context silently (Prevents Drift).
    2. PATH B: ONLY triggers Red Team if explicit 'trouble' keywords are found.
    """
    last_text = ""
    print("🧠 Trepan Brain Active: Monitoring Clipboard for Context & Threats...")
    
    while True:
        try:
            text = pyperclip.paste()
            if text != last_text and text.strip():
                last_text = text
                
                # --- PATH A: SILENT CONTEXT INJECTION (The Original Purpose) ---
                # We always update the context file so Antigravity knows what you are looking at.
                # This happens in the background. No prompts. No interruptions.
                try:
                    snippet = text[:200].replace('\n', ' ').strip()
                    if len(text) > 200:
                        snippet += "..."
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    with open(CONTEXT_FILE, "a", encoding="utf-8") as f:
                        f.write(f"\n# 🧠 USER CONTEXT ({timestamp})\n# User copied: {snippet}\n")
                except Exception:
                    pass  # Fail silently on context update

                # --- PATH B: RED TEAM TRIGGER (Only for Problems) ---
                # Only interrupt if the user looks distressed or asks for help.
                
                # Keywords that imply a BUG or a SECURITY CONCERN
                trouble_keywords = [
                    "why is", "not working", "error", "exception", "failed", 
                    "vulnerability", "exploit", "hack", "secure?", "safe?", 
                    "broken", "crash", "bug", "issue",
                    "!audit", "!attack"  # Explicit commands
                ]
                
                is_trouble = any(k in text.lower() for k in trouble_keywords)
                
                # We DO NOT trigger on just code ("def" or "import") anymore.
                # That was the mistake - it was too aggressive.
                
                if is_trouble:
                    # Identify Target File from Cache
                    target_file = "CLIPBOARD_SNIPPET"
                    found = project_cache.find_relevant_file(text)
                    if found:
                        target_file = found
                        # Quick local scan first
                        issues = scan_file_security(target_file)
                        if issues:
                            print(f"\n🔍 Pre-scan found {len(issues)} issue(s) in {target_file}")

                    # --- THE INTERRUPTION (Only when truly needed) ---
                    print("\n" + "=" * 60)
                    print(f"🕵️  INTERCEPTED: Troubleshooting/Security Context detected.")
                    print(f"🎯 Target: {target_file}")
                    print(f"❓ Trigger: '{text[:50]}...'")
                    
                    user_input = input(">>> 🧨 Launch Red Team Audit? [y/N]: ").strip().lower()
                    
                    if user_input == 'y':
                        content_to_audit = text
                        if target_file != "CLIPBOARD_SNIPPET":
                            try:
                                with open(target_file, 'r', encoding='utf-8') as f:
                                    content_to_audit = f.read()
                            except Exception as e:
                                print(f"⚠️ Could not read file: {e}")
                        
                        result = execute_red_team_attack(content_to_audit, target_file)
                        
                        if result.get('status') == 'DANGER':
                            print(f"\n🔴 DANGER DETECTED: {result['issue']}")
                            update_gemini_rules(result, target_file)
                        else:
                            print(f"\n🟢 Status: SAFE. No logical flaws detected.")
                    else:
                        print(">>> Continuing silent monitoring.")
                    print("=" * 60 + "\n")
                        
            time.sleep(1)
        except Exception as e:
            logger.error(f"Clipboard Error: {e}")
            time.sleep(1)


# =============================================================================
# 5. FILE WATCHER (The Observer - Passive AST Scanning)
# =============================================================================

class TREPANEventHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(".py"):
            return
        if "trepan.py" in event.src_path or "__pycache__" in event.src_path:
            return
        
        # Run Passive AST Scan locally (no API call)
        issues = scan_file_security(event.src_path)
        if issues:
            print("\n" + "!" * 60)
            print(f"🔴 LOCAL SECURITY ALERT in {os.path.basename(event.src_path)}:")
            for issue in issues:
                print(f"   • {issue}")
            print("!" * 60 + "\n")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    # Initialize GEMINI.md if it doesn't exist
    if not os.path.exists(CONTEXT_FILE):
        with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            f.write(f"# 🛡️ TREPAN Context File\n# Initialized: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        print(f"📝 Created {CONTEXT_FILE}")
    
    # Initialize Project Cache
    cache = ProjectCache()
    
    # Start Clipboard Monitor Thread
    clipboard_thread = threading.Thread(target=monitor_clipboard, args=(cache,), daemon=True)
    clipboard_thread.start()
    
    # Start File Watcher
    observer = Observer()
    event_handler = TREPANEventHandler()
    observer.schedule(event_handler, path=".", recursive=True)
    observer.start()
    
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║  🛡️ TREPAN 2.0 (Enterprise Edition)                               ║
║  Context Enforcer + Passive AST Defense + On-Demand Red Team      ║
╚═══════════════════════════════════════════════════════════════════╝
    """)
    print(f"👁️  Watching: {os.getcwd()}")
    print(f"📝 Context File: {CONTEXT_FILE}")
    print(f"📚 Cached Files: {len(cache.files)}")
    print("─" * 68)
    print("PATH A: Silent context updates on every clipboard copy")
    print("PATH B: Red Team prompt ONLY on trouble keywords")
    print("─" * 68)
    print("Press Ctrl+C to stop...\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 TREPAN stopped. Goodbye!")
        observer.stop()
    
    observer.join()


if __name__ == "__main__":
    main()
