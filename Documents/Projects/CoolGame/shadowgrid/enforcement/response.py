"""
ShadowGrid Enforcement Response

Graduated response system for cheating detection.
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum


class Penalty(Enum):
    """Penalty types for cheaters."""
    NONE = "none"
    WARNING = "warning"
    SHADOW_BAN = "shadow_ban"        # Match with other cheaters
    TEMP_BAN_1H = "temp_ban_1h"
    TEMP_BAN_24H = "temp_ban_24h"
    TEMP_BAN_7D = "temp_ban_7d"
    TEMP_BAN_30D = "temp_ban_30d"
    PERMANENT_BAN = "permanent_ban"


@dataclass
class PenaltyRecord:
    """Record of a penalty applied to a player."""
    record_id: str
    player_id: str
    penalty: Penalty
    reason: str
    
    # Detection info
    tier1_score: float = 0.0
    tier2_score: float = 0.0
    case_id: Optional[str] = None
    
    # Timing
    applied_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    
    # Status
    active: bool = True
    appealed: bool = False
    overturned: bool = False
    
    def is_expired(self) -> bool:
        """Check if penalty has expired."""
        if self.expires_at is None:
            return False  # Permanent
        return time.time() > self.expires_at


class EnforcementEngine:
    """
    Manages graduated response to cheating.
    
    Confidence thresholds:
    - 0.95+: Immediate permanent ban (high confidence)
    - 0.85-0.94: 7-30 day temp ban (pending review)
    - 0.70-0.84: 24h temp ban + enhanced monitoring
    - 0.50-0.69: Shadow ban (match with cheaters)
    - 0.30-0.49: Warning + enhanced monitoring
    - <0.30: No action (possible false positive)
    """
    
    # Confidence thresholds
    PERMANENT_BAN_THRESHOLD = 0.95
    TEMP_BAN_LONG_THRESHOLD = 0.85
    TEMP_BAN_SHORT_THRESHOLD = 0.70
    SHADOW_BAN_THRESHOLD = 0.50
    WARNING_THRESHOLD = 0.30
    
    def __init__(self):
        self.records: Dict[str, PenaltyRecord] = {}
        self.player_history: Dict[str, List[str]] = {}  # player_id -> record_ids
        self.shadow_pool: List[str] = []  # Players in shadow ban pool
    
    def apply_response(
        self,
        player_id: str,
        combined_score: float,
        tier1_score: float = 0.0,
        tier2_score: float = 0.0,
        case_id: Optional[str] = None,
        reason: str = ""
    ) -> PenaltyRecord:
        """
        Apply appropriate response based on detection confidence.
        
        Args:
            player_id: Player to penalize
            combined_score: Combined detection score (0-1)
            tier1_score: Score from Tier 1
            tier2_score: Score from Tier 2
            case_id: Associated case ID
            reason: Reason for penalty
            
        Returns:
            PenaltyRecord
        """
        # Check for repeat offender
        previous = self.get_player_history(player_id)
        previous_penalties = [r for r in previous if r.penalty != Penalty.NONE]
        
        # Escalate for repeat offenders
        if len(previous_penalties) > 0:
            combined_score = min(1.0, combined_score + 0.1 * len(previous_penalties))
        
        # Determine penalty
        penalty, duration = self._determine_penalty(combined_score)
        
        # Calculate expiry
        expires_at = None
        if duration:
            expires_at = time.time() + duration
        
        # Create record
        record = PenaltyRecord(
            record_id=f"pen_{uuid.uuid4().hex[:8]}",
            player_id=player_id,
            penalty=penalty,
            reason=reason or f"Auto-detected (score: {combined_score:.2%})",
            tier1_score=tier1_score,
            tier2_score=tier2_score,
            case_id=case_id,
            expires_at=expires_at
        )
        
        # Store
        self.records[record.record_id] = record
        
        if player_id not in self.player_history:
            self.player_history[player_id] = []
        self.player_history[player_id].append(record.record_id)
        
        # Apply shadow ban if needed
        if penalty == Penalty.SHADOW_BAN:
            if player_id not in self.shadow_pool:
                self.shadow_pool.append(player_id)
        
        return record
    
    def _determine_penalty(
        self,
        score: float
    ) -> tuple[Penalty, Optional[int]]:
        """
        Determine appropriate penalty based on score.
        
        Returns:
            (Penalty, duration_seconds)
        """
        if score >= self.PERMANENT_BAN_THRESHOLD:
            return Penalty.PERMANENT_BAN, None
        
        if score >= self.TEMP_BAN_LONG_THRESHOLD:
            # 7-30 days based on how high the score is
            days = 7 + int((score - self.TEMP_BAN_LONG_THRESHOLD) / 0.1 * 23)
            if days <= 7:
                return Penalty.TEMP_BAN_7D, 7 * 24 * 3600
            else:
                return Penalty.TEMP_BAN_30D, 30 * 24 * 3600
        
        if score >= self.TEMP_BAN_SHORT_THRESHOLD:
            return Penalty.TEMP_BAN_24H, 24 * 3600
        
        if score >= self.SHADOW_BAN_THRESHOLD:
            return Penalty.SHADOW_BAN, 7 * 24 * 3600  # 7 day shadow ban
        
        if score >= self.WARNING_THRESHOLD:
            return Penalty.WARNING, None
        
        return Penalty.NONE, None
    
    def check_player_status(self, player_id: str) -> dict:
        """
        Check if a player has any active penalties.
        
        Returns:
            Dict with ban status and details
        """
        records = self.get_player_history(player_id)
        
        active_penalties = [
            r for r in records
            if r.active and not r.is_expired() and not r.overturned
        ]
        
        if not active_penalties:
            return {
                'blocked': False,
                'shadow_banned': player_id in self.shadow_pool,
                'warning_count': sum(1 for r in records if r.penalty == Penalty.WARNING),
                'active_penalty': None
            }
        
        # Get most severe active penalty
        severity_order = [
            Penalty.PERMANENT_BAN,
            Penalty.TEMP_BAN_30D,
            Penalty.TEMP_BAN_7D,
            Penalty.TEMP_BAN_24H,
            Penalty.TEMP_BAN_1H,
            Penalty.SHADOW_BAN,
            Penalty.WARNING
        ]
        
        for severity in severity_order:
            for record in active_penalties:
                if record.penalty == severity:
                    return {
                        'blocked': severity in [
                            Penalty.PERMANENT_BAN,
                            Penalty.TEMP_BAN_30D,
                            Penalty.TEMP_BAN_7D,
                            Penalty.TEMP_BAN_24H,
                            Penalty.TEMP_BAN_1H
                        ],
                        'shadow_banned': player_id in self.shadow_pool,
                        'warning_count': sum(1 for r in records if r.penalty == Penalty.WARNING),
                        'active_penalty': {
                            'record_id': record.record_id,
                            'penalty': record.penalty.value,
                            'reason': record.reason,
                            'applied_at': record.applied_at,
                            'expires_at': record.expires_at
                        }
                    }
        
        return {
            'blocked': False,
            'shadow_banned': player_id in self.shadow_pool,
            'warning_count': sum(1 for r in records if r.penalty == Penalty.WARNING),
            'active_penalty': None
        }
    
    def get_player_history(self, player_id: str) -> List[PenaltyRecord]:
        """Get all penalty records for a player."""
        record_ids = self.player_history.get(player_id, [])
        return [self.records[rid] for rid in record_ids if rid in self.records]
    
    def overturn_penalty(
        self,
        record_id: str,
        reviewer_id: str,
        reason: str
    ) -> bool:
        """Overturn a penalty after appeal."""
        record = self.records.get(record_id)
        if not record:
            return False
        
        record.overturned = True
        record.active = False
        
        # Remove from shadow pool if applicable
        if record.player_id in self.shadow_pool:
            self.shadow_pool.remove(record.player_id)
        
        return True
    
    def cleanup_expired(self) -> int:
        """Clean up expired penalties. Returns count removed."""
        count = 0
        
        for record in self.records.values():
            if record.active and record.is_expired():
                record.active = False
                count += 1
                
                # Remove from shadow pool
                if record.player_id in self.shadow_pool:
                    self.shadow_pool.remove(record.player_id)
        
        return count
    
    def get_shadow_pool_players(self) -> List[str]:
        """Get list of players in shadow ban pool for matchmaking."""
        return self.shadow_pool.copy()
    
    def get_statistics(self) -> dict:
        """Get enforcement statistics."""
        total = len(self.records)
        active = sum(1 for r in self.records.values() if r.active and not r.is_expired())
        
        penalty_counts = {}
        for penalty in Penalty:
            penalty_counts[penalty.value] = sum(
                1 for r in self.records.values() if r.penalty == penalty
            )
        
        return {
            'total_penalties': total,
            'active_penalties': active,
            'shadow_pool_size': len(self.shadow_pool),
            'penalty_breakdown': penalty_counts,
            'appeal_rate': sum(1 for r in self.records.values() if r.appealed) / max(total, 1),
            'overturn_rate': sum(1 for r in self.records.values() if r.overturned) / max(total, 1)
        }


# Global instance
enforcement_engine = EnforcementEngine()
