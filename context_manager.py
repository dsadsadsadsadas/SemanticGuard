#!/usr/bin/env python3
"""
📜 TREPAN Context Manager (TR-04)
The "Legislator" database engine - writes decisions in Diamond schema to GEMINI.md.

Diamonds are permanent decision records with:
- Unique ID
- The Law (what rule this enforces)
- The Why (reasoning/context)
- Code snapshot as evidence
"""

import time
import os
import uuid

GEMINI_FILE = "GEMINI.md"


class ContextManager:
    """
    Manages structured context entries ("Diamonds") in GEMINI.md.
    Prevents the "Junk Drawer" problem with consistent formatting.
    """
    
    def __init__(self):
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create GEMINI.md with proper header if it doesn't exist."""
        if not os.path.exists(GEMINI_FILE):
            with open(GEMINI_FILE, "w", encoding="utf-8") as f:
                f.write("# 🧠 TREPAN PROJECT CONTEXT (The Constitution)\n")
                f.write("## 💎 Active Decision Diamonds\n\n")

    def log_diamond(self, drift_score: float, code_snippet: str, 
                    intent_law: str, intent_why: str) -> bool:
        """
        Write a 'Diamond' entry - a permanent decision record.
        
        Args:
            drift_score: The semantic drift score that triggered this
            code_snippet: The code that was approved
            intent_law: What rule/pattern this enforces
            intent_why: Reasoning behind the decision
            
        Returns:
            True if successfully written, False otherwise
        """
        # Generate unique short ID (last 6 chars of UUID for brevity)
        diamond_id = f"D-{str(uuid.uuid4())[:6].upper()}"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Sanitize code snippet
        safe_snippet = code_snippet.strip()[:500].replace("```", "'''")
        
        entry = f"""
---
## 💎 [{diamond_id}] - Intent: {intent_law}
**Timestamp:** {timestamp} | **Status:** ACTIVE
**Drift Score:** {drift_score:.2f} (High Value Signal)

**⚖️ The Law:**
> {intent_law}

**🤔 The Why:**
{intent_why}

**📜 Snapshot (Evidence):**
```python
{safe_snippet}
# ... (Check git for full diff)
```

"""
        try:
            with open(GEMINI_FILE, "a", encoding="utf-8") as f:
                f.write(entry)
            print(f"[*] 💎 Diamond {diamond_id} Minted in {GEMINI_FILE}")
            return True
        except Exception as e:
            print(f"[!] Context Write Error: {e}")
            return False
    
    def log_block(self, drift_score: float, blocked_snippet: str) -> bool:
        """
        Log a BLOCK decision for audit purposes.
        
        Args:
            drift_score: The drift score that triggered this
            blocked_snippet: The code that was blocked
            
        Returns:
            True if successfully written
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        entry = f"""
---
## 🚫 BLOCKED - {timestamp}
**Drift Score:** {drift_score:.2f}
**Reason:** User explicitly blocked this high-drift content.

**Blocked Content Preview:**
```
{blocked_snippet[:100]}...
```

"""
        try:
            with open(GEMINI_FILE, "a", encoding="utf-8") as f:
                f.write(entry)
            return True
        except Exception:
            return False


# Global Instance
context_db = ContextManager()
