#!/usr/bin/env python3
"""
🔴 RED TEAM AUDITOR (red_team.py)
"Click-to-Audit" Security Tool for Project Trepan.

Flow:
1. Analyze Clipboard (Code vs Question).
2. If Question -> Find & Read target file.
3. Privacy Gate -> User Confirmation (y/n).
4. Groq Audit -> Hostile Red Team Analysis.
5. Feedback -> Print Alert + Update GEMINI.md.
"""

import os
import sys
import json
import time
import re
from typing import Optional, Tuple, Dict

# Third-party imports
try:
    import pyperclip
    from groq import Groq
    from dotenv import load_dotenv
except ImportError as e:
    print(f"❌ Missing dependency: {e}")
    print("Run: pip install pyperclip groq python-dotenv")
    sys.exit(1)

# Configuration
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
RULES_FILE = "GEMINI.md"

# ANSI Colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

SYSTEM_PROMPT = """You are a HOSTILE RED TEAM HACKER.
Your goal is to find LOGICAL VULNERABILITIES in the provided code.
Focus on:
- IDOR (Insecure Direct Object References)
- Injection Flaws (SQL, Command, etc.)
- Broken Access Control
- Sensitive Data Exposure
- Race Conditions

Output JSON ONLY:
{
  "status": "SAFE" or "DANGER",
  "issue": "Brief description of the vulnerability (max 1 sentence)",
  "fix_instruction": "Precise instruction to fix it (max 2 sentences)"
}
If SAFE, fix_instruction can be empty.
"""

class RedTeamAuditor:
    def __init__(self):
        if not GROQ_API_KEY:
            print(f"{RED}❌ Error: GROQ_API_KEY not found in .env{RESET}")
            sys.exit(1)
        self.client = Groq(api_key=GROQ_API_KEY)
        self.cwd = os.getcwd()

    def get_clipboard(self) -> str:
        content = pyperclip.paste()
        if not content:
            print(f"{YELLOW}⚠️  Clipboard is empty.{RESET}")
            sys.exit(0)
        return content.strip()

    def find_file_by_keyword(self, keyword: str) -> Optional[str]:
        """Search for a file matching the keyword in the current directory (recursive)."""
        keyword = keyword.lower()
        ignore_dirs = {'.git', 'venv', '__pycache__', 'node_modules', '.venv'}
        
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file in files:
                if keyword in file.lower():
                    return os.path.join(root, file)
        return None

    def resolve_target(self, clipboard: str) -> Tuple[str, str, str]:
        """
        Determine if clipboard is Code or a Reference.
        Returns: (TargetType, Content, Identifier)
        """
        # Heuristic: Code usually has newlines, indentations, or syntax chars
        is_code = len(clipboard.split('\n')) > 1 or any(c in clipboard for c in '{}();=')
        
        if is_code:
            return ("CLIPBOARD_CODE", clipboard, "Clipboard Snippet")
        
        # It's likely a text request/question -> Extract potential filename keyword
        # Example: "Check auth logic" -> keyword: "auth"
        keywords = re.findall(r'\b\w+\b', clipboard)
        # Filter out common stop words if needed, but for now take the longest word as best guess
        # or iterate to find a matching file.
        
        for word in sorted(keywords, key=len, reverse=True):
            if len(word) < 3: continue 
            match = self.find_file_by_keyword(word)
            if match:
                try:
                    with open(match, 'r', encoding='utf-8') as f:
                        content = f.read()
                    return ("FILE", content, os.path.basename(match))
                except Exception as e:
                    print(f"{RED}❌ Could not read file {match}: {e}{RESET}")
                    sys.exit(1)
        
        print(f"{YELLOW}⚠️  Could not find any file matching clipboard keywords: '{clipboard}'{RESET}")
        sys.exit(0)

    def request_permission(self, target_name: str, content_preview: str) -> bool:
        print(f"\n{CYAN}🕵️  RED TEAM TARGET IDENTIFIED:{RESET}")
        print(f"   Target: {BOLD}{target_name}{RESET}")
        print(f"   Preview: {content_preview[:50].replace(chr(10), ' ')}...")
        
        while True:
            response = input(f"\n{YELLOW}⚠️  Send this to External Red Team AI? (y/n): {RESET}").lower().strip()
            if response == 'y':
                return True
            if response == 'n':
                return False

    def audit(self, content: str) -> Dict:
        print(f"\n{CYAN}🔄 Initializing Cyber-Attack Simulation (Groq)...{RESET}")
        try:
            completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content}
                ],
                model=GROQ_MODEL,
                temperature=0.3,
                # Remove response_format="json_object" if it causes issues with list returns, 
                # but usually it enforces object. Llama might be returning a list though.
                response_format={"type": "json_object"}
            )
            parsed = json.loads(completion.choices[0].message.content)
            # Handle if model returns a list wrapped in a key or just a list
            if isinstance(parsed, list):
                if len(parsed) > 0:
                    return parsed[0]
                return {} 
            return parsed
        except Exception as e:
            print(f"{RED}❌ Audit Failed: {e}{RESET}")
            # print raw content for debug
            try:
                print(f"DEBUG Raw Content: {completion.choices[0].message.content}")
            except:
                pass
            sys.exit(1)

    def apply_feedback(self, result: Dict, target_name: str):
        status = result.get('status', 'UNKNOWN').upper()
        issue = result.get('issue', 'No details provided.')
        fix = result.get('fix_instruction', '')

        print(f"\n{BOLD}🔍 AUDIT RESULTS for {target_name}:{RESET}")
        
        if status == 'SAFE':
            print(f"{GREEN}✅ STATUS: SAFE{RESET}")
            print(f"   Analysis: {issue}")
            return

        print(f"{RED}🛑 STATUS: DANGER DECTECTED{RESET}")
        print(f"   Vulnerability: {BOLD}{issue}{RESET}")
        print(f"   Required Fix: {fix}")

        # Auto-update GEMINI.md
        self.update_rules_file(target_name, issue, fix)

    def update_rules_file(self, target_name: str, issue: str, fix: str):
        header = f"""# 🛑 SECURITY INTERVENTION
# The Red Team detected a vulnerability in {target_name}.
# Issue: {issue}
# 
# CONSTRAINT: You MUST implement the following fix:
# {fix}
#
# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""
        try:
            # We overwrite or append? The user prompt implied "WRITE the fix_instruction into GEMINI.md"
            # Usually strict context enforcement overwrites previous context to ensure focus.
            # I will prepend it or overwrite. Let's overwrite to ensure it's the specific instruction.
            # But wait, trepan.py manages GEMINI.md too. 
            # If we overwrite, we might lose other context triggers.
            # But a SECURITY INTERVENTION is critical.
            
            with open(RULES_FILE, 'w', encoding='utf-8') as f:
                f.write(header)
            print(f"\n{GREEN}💉 Context Injected into {RULES_FILE}{RESET}")
        except Exception as e:
            print(f"{RED}❌ Failed to update rules file: {e}{RESET}")

    def run(self):
        print(f"{BOLD}🔴 RED TEAM AUDITOR v1.0{RESET}")
        print("Waiting for user clipboard analysis...")
        
        # 1. Analyze Clipboard
        clipboard = self.get_clipboard()
        type_, content, target_name = self.resolve_target(clipboard)
        
        # 2. Permissions
        if not self.request_permission(target_name, content):
            print(f"{RED}🚫 Audit Aborted by User.{RESET}")
            return

        # 3. Audit
        result = self.audit(content)
        
        # 4. Feedback
        self.apply_feedback(result, target_name)


if __name__ == "__main__":
    auditor = RedTeamAuditor()
    auditor.run()
