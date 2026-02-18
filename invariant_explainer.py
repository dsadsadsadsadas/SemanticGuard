#!/usr/bin/env python3
"""
⚖️ TREPAN Invariant Explainer (TR-10.5)
Human-Readable Reasoning for Blocks & Alerts.

Converts raw signals → explicit violated principles.
No AI. No guessing. Deterministic explanation mapping.

Design Philosophy:
- Trepan does not judge intent
- Trepan explains principles, not consequences
- Clarity beats cleverness
- One sentence is enough if it's the right one
"""

from typing import Dict, Any, Optional, List


class InvariantExplainer:
    """
    Generates human-readable explanations for security violations.
    
    Priority order (highest wins):
    1. Regex hits (execution, secrets, filesystem)
    2. Phase violations
    3. Shrinkage during HARDENING
    4. High drift without intent
    5. Fallback: generic integrity warning
    """
    
    # Static Invariant Definitions
    INVARIANTS = {
        "NO_EXECUTION_PRIMITIVES": {
            "id": "INV-001",
            "description": "Arbitrary execution APIs require manual approval.",
            "severity": "CRITICAL"
        },
        "NO_SECRET_EXPOSURE": {
            "id": "INV-002",
            "description": "Credentials and secrets must not appear in code.",
            "severity": "CRITICAL"
        },
        "NO_FILESYSTEM_DESTRUCTION": {
            "id": "INV-003",
            "description": "Destructive filesystem operations require explicit review.",
            "severity": "CRITICAL"
        },
        "NO_NETWORK_EXFILTRATION": {
            "id": "INV-004",
            "description": "Network access patterns require explicit approval.",
            "severity": "HIGH"
        },
        "NO_CRYPTO_WEAKENING": {
            "id": "INV-005",
            "description": "Cryptographic strength must not be reduced without review.",
            "severity": "HIGH"
        },
        "NO_SHRINKAGE_IN_HARDENING": {
            "id": "INV-006",
            "description": "Code reduction during hardening is suspicious.",
            "severity": "HIGH"
        },
        "NO_SILENT_SECURITY_REGRESSION": {
            "id": "INV-007",
            "description": "Security-critical logic must not weaken without explicit review.",
            "severity": "HIGH"
        },
        "NO_CONTEXT_FREE_REWRITE": {
            "id": "INV-008",
            "description": "Large semantic drift requires intent confirmation.",
            "severity": "MEDIUM"
        },
        "PHASE_VIOLATION": {
            "id": "INV-009",
            "description": "Behavior conflicts with current development phase.",
            "severity": "MEDIUM"
        },
        "GENERIC_INTEGRITY": {
            "id": "INV-999",
            "description": "Change integrity could not be verified.",
            "severity": "LOW"
        }
    }
    
    # Regex category → Invariant mapping
    REGEX_TO_INVARIANT = {
        "EXECUTION": "NO_EXECUTION_PRIMITIVES",
        "SECRETS": "NO_SECRET_EXPOSURE",
        "FILESYSTEM": "NO_FILESYSTEM_DESTRUCTION",
        "NETWORK": "NO_NETWORK_EXFILTRATION",
        "CRYPTO_WEAKENING": "NO_CRYPTO_WEAKENING"
    }
    
    def __init__(self):
        pass
    
    def explain(self, event_context: Dict[str, Any]) -> str:
        """
        Generate a single, clear explanation sentence.
        
        Args:
            event_context: {
                "phase": "HARDENING",
                "drift_score": 0.62,
                "shrinkage_ratio": 0.38,
                "regex_hits": ["EXECUTION:os.system"],
                "lane": "LOUD",
                "file_context": "auth.py",
                "tags": ["security", "auth"]
            }
            
        Returns:
            A single explanatory sentence with cause → consequence structure.
        """
        # Extract context (with defaults for missing fields)
        phase = event_context.get("phase", "NORMAL_FLOW")
        drift_score = event_context.get("drift_score", 0.0)
        shrinkage_ratio = event_context.get("shrinkage_ratio", 1.0)
        regex_hits = event_context.get("regex_hits", [])
        file_context = event_context.get("file_context", "unknown file")
        tags = event_context.get("tags", [])
        
        # ==========================================
        # PRIORITY 1: Regex Hits (Highest Priority)
        # ==========================================
        if regex_hits:
            return self._explain_regex_hit(regex_hits, file_context)
        
        # ==========================================
        # PRIORITY 2: Shrinkage during HARDENING
        # ==========================================
        if shrinkage_ratio < 0.5 and phase == "HARDENING":
            reduction_pct = int((1 - shrinkage_ratio) * 100)
            return (
                f"This change removes {reduction_pct}% of code during a HARDENING phase, "
                f"violating the rule against simplifying security-critical logic."
            )
        
        # ==========================================
        # PRIORITY 3: Phase Violation
        # ==========================================
        if phase == "HARDENING" and drift_score > 0.5:
            return (
                f"High semantic drift ({drift_score:.0%}) occurred during HARDENING phase, "
                f"where stability is expected. Large changes require explicit review."
            )
        
        # ==========================================
        # PRIORITY 4: Shrinkage (Non-HARDENING)
        # ==========================================
        if shrinkage_ratio < 0.5:
            reduction_pct = int((1 - shrinkage_ratio) * 100)
            return (
                f"This change reduces code by {reduction_pct}%, "
                f"which may indicate accidental deletion of important logic."
            )
        
        # ==========================================
        # PRIORITY 5: High Drift
        # ==========================================
        if drift_score >= 0.7:
            return (
                f"Large semantic drift ({drift_score:.0%}) detected without declared intent, "
                f"risking silent logic regression."
            )
        
        if drift_score >= 0.5:
            return (
                f"Moderate semantic drift ({drift_score:.0%}) detected. "
                f"Changes of this magnitude require confirmation to prevent unintended modifications."
            )
        
        # ==========================================
        # PRIORITY 6: Security-Related Tags
        # ==========================================
        security_tags = {"security", "auth", "crypto", "secret", "password", "token"}
        if set(tags) & security_tags:
            return (
                f"This change affects security-related code (tags: {', '.join(set(tags) & security_tags)}), "
                f"which requires explicit review regardless of drift score."
            )
        
        # ==========================================
        # FALLBACK: Generic Integrity Warning
        # ==========================================
        return (
            f"Change integrity could not be fully verified. "
            f"Manual review is required before proceeding."
        )
    
    def _explain_regex_hit(self, regex_hits: List[str], file_context: str) -> str:
        """
        Generate explanation for regex pattern matches.
        
        Args:
            regex_hits: List of "CATEGORY:pattern" strings
            file_context: The file being modified
        """
        # Parse first hit for explanation
        first_hit = regex_hits[0] if regex_hits else ""
        
        if ":" in first_hit:
            category, pattern = first_hit.split(":", 1)
        else:
            category = "EXECUTION"
            pattern = first_hit
        
        # Map category to invariant
        invariant_key = self.REGEX_TO_INVARIANT.get(category, "NO_EXECUTION_PRIMITIVES")
        invariant = self.INVARIANTS.get(invariant_key, {})
        
        # Generate category-specific explanation
        if category == "EXECUTION":
            return (
                f"An execution primitive ({pattern}) was introduced, "
                f"which is disallowed without explicit review per {invariant.get('id', 'INV-001')}."
            )
        
        if category == "SECRETS":
            return (
                f"A credential or secret pattern was detected in the code, "
                f"violating {invariant.get('id', 'INV-002')}: secrets must not appear in source."
            )
        
        if category == "FILESYSTEM":
            return (
                f"A destructive filesystem operation ({pattern}) was detected, "
                f"requiring manual approval per {invariant.get('id', 'INV-003')}."
            )
        
        if category == "NETWORK":
            return (
                f"A network access pattern ({pattern}) was detected, "
                f"which requires explicit review for potential data exfiltration."
            )
        
        if category == "CRYPTO_WEAKENING":
            return (
                f"A weak cryptographic pattern ({pattern}) was detected, "
                f"which may compromise security strength."
            )
        
        # Fallback for unknown category
        return (
            f"A critical pattern ({pattern}) was detected, "
            f"requiring manual review before proceeding."
        )
    
    def get_violated_invariant(self, event_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return the specific invariant that was violated.
        
        Returns:
            {
                "id": "INV-001",
                "key": "NO_EXECUTION_PRIMITIVES",
                "description": "...",
                "severity": "CRITICAL"
            }
        """
        regex_hits = event_context.get("regex_hits", [])
        phase = event_context.get("phase", "NORMAL_FLOW")
        shrinkage_ratio = event_context.get("shrinkage_ratio", 1.0)
        drift_score = event_context.get("drift_score", 0.0)
        
        # Priority 1: Regex
        if regex_hits:
            first_hit = regex_hits[0]
            category = first_hit.split(":")[0] if ":" in first_hit else "EXECUTION"
            key = self.REGEX_TO_INVARIANT.get(category, "NO_EXECUTION_PRIMITIVES")
            inv = self.INVARIANTS.get(key, self.INVARIANTS["GENERIC_INTEGRITY"])
            return {"key": key, **inv}
        
        # Priority 2: Shrinkage in HARDENING
        if shrinkage_ratio < 0.5 and phase == "HARDENING":
            key = "NO_SHRINKAGE_IN_HARDENING"
            return {"key": key, **self.INVARIANTS[key]}
        
        # Priority 3: Phase violation
        if phase == "HARDENING" and drift_score > 0.5:
            key = "PHASE_VIOLATION"
            return {"key": key, **self.INVARIANTS[key]}
        
        # Priority 4: Shrinkage
        if shrinkage_ratio < 0.5:
            key = "NO_SILENT_SECURITY_REGRESSION"
            return {"key": key, **self.INVARIANTS[key]}
        
        # Priority 5: High drift
        if drift_score >= 0.5:
            key = "NO_CONTEXT_FREE_REWRITE"
            return {"key": key, **self.INVARIANTS[key]}
        
        # Fallback
        key = "GENERIC_INTEGRITY"
        return {"key": key, **self.INVARIANTS[key]}


# Global instance
explainer = InvariantExplainer()
