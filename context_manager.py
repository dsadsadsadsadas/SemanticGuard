#!/usr/bin/env python3
"""
📜 TREPAN Context Manager (TR-04 + TR-10)
The "Legislator" database engine - writes decisions in Diamond schema to GEMINI.md.

TR-10: Extended with Micro-Data footer for phase context and cognitive metadata.

Diamonds are permanent decision records with:
- Unique ID
- The Law (what rule this enforces)
- The Why (reasoning/context)
- Code snapshot as evidence
- Micro-Data (phase, velocity, drift context)
"""

import time
import os
import uuid
from typing import Optional, Dict, Any

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

    def log_diamond(
        self, 
        drift_score: float, 
        code_snippet: str, 
        intent_law: str, 
        intent_why: str,
        phase_context: Optional[Dict[str, Any]] = None,
        explanation: Optional[str] = None
    ) -> bool:
        """
        Write a 'Diamond' entry - a permanent decision record.
        
        Args:
            drift_score: The semantic drift score that triggered this
            code_snippet: The code that was approved
            intent_law: What rule/pattern this enforces
            intent_why: Reasoning behind the decision
            phase_context: TR-10 phase detection context (optional)
            explanation: TR-10.5 invariant explanation (optional)
            
        Returns:
            True if successfully written, False otherwise
        """
        # Generate unique short ID
        diamond_id = f"D-{str(uuid.uuid4())[:6].upper()}"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Sanitize code snippet
        safe_snippet = code_snippet.strip()[:500].replace("```", "'''")
        
        # Build main entry
        entry = f"""
---
## 💎 [{diamond_id}] - Intent: {intent_law}
**Timestamp:** {timestamp} | **Status:** ACTIVE
**Drift Score:** {drift_score:.2f} (High Value Signal)

**⚖️ The Law:**
> {intent_law}

**🤔 The Why:**
{intent_why}

"""
        
        # TR-10.5: Add invariant violation explanation
        if explanation:
            entry += f"""**⚠️ Invariant Violation:**
> {explanation}

"""
        
        # Add code snapshot
        entry += f"""**📜 Snapshot (Evidence):**
```python
{safe_snippet}
# ... (Check git for full diff)
```

"""
        
        # TR-10: Add Micro-Data footer if phase context provided
        if phase_context:
            micro_data = self._build_micro_data(phase_context, drift_score)
            entry += micro_data
        
        try:
            with open(GEMINI_FILE, "a", encoding="utf-8") as f:
                f.write(entry)
            print(f"[*] 💎 Diamond {diamond_id} Minted in {GEMINI_FILE}")
            return True
        except Exception as e:
            print(f"[!] Context Write Error: {e}")
            return False
    
    def _build_micro_data(self, phase_context: Dict[str, Any], drift_score: float) -> str:
        """
        TR-10: Build Micro-Data footer for cognitive context.
        
        This metadata helps future AI assistants understand
        the project's evolution and the context of each decision.
        """
        phase_name = phase_context.get("phase_name", "NORMAL_FLOW")
        icon = phase_context.get("icon", "📋")
        confidence = phase_context.get("confidence", 1.0)
        signals = phase_context.get("signals", [])
        threshold = phase_context.get("recommended_threshold", 0.4)
        
        # Determine velocity indicator
        velocity = "Normal"
        if "high_velocity" in signals:
            velocity = "High"
        elif len(signals) > 3:
            velocity = "Active"
        
        # Determine risk level
        risk = "Low"
        if drift_score >= 0.8:
            risk = "Critical"
        elif drift_score >= 0.6:
            risk = "High"
        elif drift_score >= 0.4:
            risk = "Medium"
        
        micro_data = f"""> **📊 Micro-Data (TR-10):**
> | Key | Value |
> |-----|-------|
> | `phase` | {icon} {phase_name} |
> | `confidence` | {confidence:.0%} |
> | `velocity` | {velocity} |
> | `drift_risk` | {risk} ({drift_score:.2f}) |
> | `threshold` | {threshold} |
> | `signals` | {', '.join(signals) if signals else 'none'} |

"""
        return micro_data
    
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
