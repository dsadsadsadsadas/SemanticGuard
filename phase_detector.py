#!/usr/bin/env python3
"""
🧠 TREPAN Phase Detector (TR-10)
Cognitive Phase Detection & Paranoia Biasing.

Analyzes recent ledger history to infer the developer's working phase
and adjusts Trepan's alert sensitivity accordingly.

DESIGN GUARANTEES:
- Phase is advisory, not authoritative
- Regex matches and hard blocks ALWAYS override phase logic
- Uncertainty is visible via confidence score
- Silence is never mistaken for safety
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

LEDGER_FILE = "draft_ledger.json"
MAX_ENTRIES_TO_ANALYZE = 20


class PhaseDetector:
    """
    Lightweight phase inference module.
    
    Analyzes the last N ledger entries to detect:
    - HARDENING: Security-focused work, high paranoia
    - PROTOTYPING: Rapid iteration, lower sensitivity
    - DEBUGGING: Repetitive targeted changes
    - NORMAL_FLOW: Default behavior when uncertain
    """
    
    # Phase configurations
    PHASES = {
        "HARDENING": {
            "icon": "🛡️",
            "description": "Security-critical or stabilizing work detected.",
            "recommended_threshold": 0.30,
            "silent_mode": False
        },
        "PROTOTYPING": {
            "icon": "🚀",
            "description": "Rapid iteration and new feature development detected.",
            "recommended_threshold": 0.55,
            "silent_mode": True
        },
        "DEBUGGING": {
            "icon": "🔧",
            "description": "Targeted debugging and fix iteration detected.",
            "recommended_threshold": 0.40,
            "silent_mode": True
        },
        "NORMAL_FLOW": {
            "icon": "📋",
            "description": "Standard working mode, default sensitivity.",
            "recommended_threshold": 0.40,
            "silent_mode": True
        }
    }
    
    # Tag trust levels (tags are hints, not authority)
    HARDENING_TAGS = {"security", "auth", "regex", "fix", "validation", "crypto", "secret"}
    PROTOTYPING_TAGS = {"new_feature", "import", "scaffold", "init", "create", "api"}
    DEBUGGING_TAGS = {"bug", "debug", "fix", "error", "test", "print"}
    
    def __init__(self, ledger_path: str = LEDGER_FILE):
        self.ledger_path = ledger_path
        self.logger = logging.getLogger("Trepan.Phase")
    
    def _read_tail_entries(self, max_entries: int = MAX_ENTRIES_TO_ANALYZE) -> List[Dict]:
        """
        Read only the last N entries from the ledger.
        Handles missing or malformed files gracefully.
        """
        if not os.path.exists(self.ledger_path):
            return []
        
        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                entries = data.get("entries", [])
                return entries[-max_entries:]  # Tail only
        except (json.JSONDecodeError, KeyError, TypeError):
            return []
    
    def _calculate_velocity(self, entries: List[Dict]) -> float:
        """
        Calculate events-per-minute over the analyzed window.
        """
        if len(entries) < 2:
            return 0.0
        
        try:
            timestamps = [datetime.fromisoformat(e["timestamp"]) for e in entries if "timestamp" in e]
            if len(timestamps) < 2:
                return 0.0
            
            time_span = (timestamps[-1] - timestamps[0]).total_seconds() / 60.0  # minutes
            if time_span <= 0:
                return 0.0
            
            return len(entries) / time_span
        except Exception:
            return 0.0
    
    def _check_file_repetition(self, entries: List[Dict]) -> int:
        """
        Count how many times the same file was modified in recent entries.
        Returns max repetition count for any single file.
        """
        file_counts: Dict[str, int] = {}
        for entry in entries:
            file_path = entry.get("file_path") or entry.get("source_app", "unknown")
            file_counts[file_path] = file_counts.get(file_path, 0) + 1
        
        return max(file_counts.values()) if file_counts else 0
    
    def _compute_phase_scores(self, entries: List[Dict]) -> Dict[str, float]:
        """
        Compute weighted scores for each phase based on structural signals.
        Tags are LOW trust (weight 0.5). Structural signals are HIGH trust (weight 1-2).
        """
        scores = {
            "HARDENING": 0.0,
            "PROTOTYPING": 0.0,
            "DEBUGGING": 0.0
        }
        
        if not entries:
            return scores
        
        signals_used = []
        
        for entry in entries:
            drift = entry.get("drift_score", 0.0)
            multiplier = entry.get("paranoia_multiplier", 1.0)
            shrinkage = entry.get("shrinkage_ratio", 1.0)
            regex_hit = entry.get("regex_hit", False)
            tags = set(t.lower() for t in entry.get("tags", []))
            
            # ========== HARDENING SIGNALS ==========
            # Regex hit is STRONG signal (weight 2)
            if regex_hit:
                scores["HARDENING"] += 2.0
                signals_used.append("regex_hit")
            
            # High drift is suspicious (weight 1)
            if drift >= 0.7:
                scores["HARDENING"] += 1.0
                signals_used.append("high_drift")
            
            # Shrinkage detected (weight 1)
            if shrinkage < 0.7 or multiplier > 1.0:
                scores["HARDENING"] += 1.0
                signals_used.append("shrinkage")
            
            # Security-related tags (weight 0.5 - low trust)
            if tags & self.HARDENING_TAGS:
                scores["HARDENING"] += 0.5
            
            # ========== PROTOTYPING SIGNALS ==========
            # Low drift = stable additions (weight 1)
            if drift < 0.4:
                scores["PROTOTYPING"] += 1.0
            
            # Prototyping tags (weight 0.5)
            if tags & self.PROTOTYPING_TAGS:
                scores["PROTOTYPING"] += 0.5
            
            # ========== DEBUGGING SIGNALS ==========
            # Medium drift (weight 0.5)
            if 0.4 <= drift < 0.6:
                scores["DEBUGGING"] += 0.5
            
            # Debugging tags (weight 0.5)
            if tags & self.DEBUGGING_TAGS:
                scores["DEBUGGING"] += 0.5
        
        # Global velocity signal
        velocity = self._calculate_velocity(entries)
        if velocity > 5.0:  # >5 events per minute = rapid iteration
            scores["PROTOTYPING"] += 2.0
            signals_used.append("high_velocity")
        
        # File repetition = debugging
        max_rep = self._check_file_repetition(entries)
        if max_rep >= 3:
            scores["DEBUGGING"] += 2.0
            signals_used.append("file_repetition")
        
        return scores
    
    def get_current_phase(self) -> Dict[str, Any]:
        """
        Analyze recent history and return the detected phase.
        
        Returns:
            {
                "phase_name": "HARDENING",
                "icon": "🛡️",
                "confidence": 0.76,
                "description": "...",
                "recommended_threshold": 0.3,
                "silent_mode": False,
                "signals": ["regex_hits", "shrinkage"]
            }
        """
        entries = self._read_tail_entries()
        
        if not entries:
            return self._build_result("NORMAL_FLOW", 1.0, [])
        
        scores = self._compute_phase_scores(entries)
        total_score = sum(scores.values())
        
        if total_score == 0:
            return self._build_result("NORMAL_FLOW", 1.0, [])
        
        # Find winning phase
        winning_phase = max(scores, key=scores.get)
        winning_score = scores[winning_phase]
        confidence = winning_score / total_score
        
        # If confidence is too low, fall back to NORMAL_FLOW
        if confidence < 0.4:
            return self._build_result("NORMAL_FLOW", confidence, self._extract_signals(entries))
        
        return self._build_result(winning_phase, confidence, self._extract_signals(entries))
    
    def _extract_signals(self, entries: List[Dict]) -> List[str]:
        """Extract notable signals for display."""
        signals = []
        
        if any(e.get("regex_hit") for e in entries):
            signals.append("regex_hits")
        
        if any(e.get("paranoia_multiplier", 1.0) > 1.0 for e in entries):
            signals.append("shrinkage")
        
        avg_drift = sum(e.get("drift_score", 0) for e in entries) / max(len(entries), 1)
        if avg_drift >= 0.6:
            signals.append("high_drift")
        elif avg_drift < 0.4:
            signals.append("low_drift")
        
        velocity = self._calculate_velocity(entries)
        if velocity > 5.0:
            signals.append("high_velocity")
        
        return signals
    
    def _build_result(self, phase_name: str, confidence: float, signals: List[str]) -> Dict[str, Any]:
        """Build the result dictionary."""
        phase_config = self.PHASES.get(phase_name, self.PHASES["NORMAL_FLOW"])
        
        return {
            "phase_name": phase_name,
            "icon": phase_config["icon"],
            "confidence": round(confidence, 2),
            "description": phase_config["description"],
            "recommended_threshold": phase_config["recommended_threshold"],
            "silent_mode": phase_config["silent_mode"],
            "signals": signals
        }
    
    def get_threshold_for_phase(self, phase_name: str) -> float:
        """Get recommended drift threshold for a phase."""
        return self.PHASES.get(phase_name, self.PHASES["NORMAL_FLOW"])["recommended_threshold"]
    
    def should_enable_silent_mode(self, phase_name: str) -> bool:
        """Whether silent mode is recommended for the phase."""
        return self.PHASES.get(phase_name, self.PHASES["NORMAL_FLOW"])["silent_mode"]


# Global instance
phase_detector = PhaseDetector()
