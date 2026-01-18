"""
ShadowGrid Tier 3 Case Manager

Manages cases for expert human review.
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum
from datetime import datetime
import json


class CaseStatus(Enum):
    """Status of a case in the review queue."""
    PENDING = "pending"         # Waiting for review
    IN_REVIEW = "in_review"     # Being reviewed
    CLEARED = "cleared"         # Found innocent
    BANNED = "banned"           # Confirmed cheater
    MONITORING = "monitoring"   # Not enough evidence, watching
    ESCALATED = "escalated"     # Needs senior review


class CasePriority(Enum):
    """Priority level for case review."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class CaseEvidence:
    """Evidence attached to a case."""
    evidence_id: str
    evidence_type: str  # 'replay', 'stats', 'visual', 'log'
    description: str
    data: Dict
    created_at: float = field(default_factory=time.time)


@dataclass
class CaseNote:
    """Note from a reviewer."""
    note_id: str
    reviewer_id: str
    content: str
    created_at: float = field(default_factory=time.time)


@dataclass
class Case:
    """A case requiring expert review."""
    case_id: str
    player_id: str
    
    # Status
    status: CaseStatus = CaseStatus.PENDING
    priority: CasePriority = CasePriority.MEDIUM
    
    # Timing
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    # Detection info
    tier1_score: float = 0.0
    tier2_score: float = 0.0
    combined_score: float = 0.0
    detection_source: str = "tier2"
    
    # AI analysis
    ai_verdict: str = ""
    ai_confidence: float = 0.0
    ai_reasoning: str = ""
    top_features: List[tuple] = field(default_factory=list)
    
    # Human review
    assigned_to: Optional[str] = None
    reviewed_by: Optional[str] = None
    final_verdict: Optional[str] = None
    human_notes: str = ""
    
    # Evidence
    evidence: List[CaseEvidence] = field(default_factory=list)
    notes: List[CaseNote] = field(default_factory=list)
    
    # Sessions
    replay_ids: List[str] = field(default_factory=list)
    session_ids: List[str] = field(default_factory=list)
    
    def add_evidence(
        self,
        evidence_type: str,
        description: str,
        data: Dict
    ) -> CaseEvidence:
        """Add evidence to the case."""
        evidence = CaseEvidence(
            evidence_id=f"ev_{uuid.uuid4().hex[:8]}",
            evidence_type=evidence_type,
            description=description,
            data=data
        )
        self.evidence.append(evidence)
        self.updated_at = time.time()
        return evidence
    
    def add_note(self, reviewer_id: str, content: str) -> CaseNote:
        """Add a reviewer note."""
        note = CaseNote(
            note_id=f"note_{uuid.uuid4().hex[:8]}",
            reviewer_id=reviewer_id,
            content=content
        )
        self.notes.append(note)
        self.updated_at = time.time()
        return note
    
    def to_dict(self) -> dict:
        """Convert case to dictionary."""
        return {
            'case_id': self.case_id,
            'player_id': self.player_id,
            'status': self.status.value,
            'priority': self.priority.value,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'tier1_score': self.tier1_score,
            'tier2_score': self.tier2_score,
            'combined_score': self.combined_score,
            'detection_source': self.detection_source,
            'ai_verdict': self.ai_verdict,
            'ai_confidence': self.ai_confidence,
            'ai_reasoning': self.ai_reasoning,
            'top_features': self.top_features,
            'assigned_to': self.assigned_to,
            'reviewed_by': self.reviewed_by,
            'final_verdict': self.final_verdict,
            'human_notes': self.human_notes,
            'evidence': [
                {
                    'evidence_id': e.evidence_id,
                    'evidence_type': e.evidence_type,
                    'description': e.description,
                    'created_at': e.created_at
                }
                for e in self.evidence
            ],
            'notes': [
                {
                    'note_id': n.note_id,
                    'reviewer_id': n.reviewer_id,
                    'content': n.content,
                    'created_at': n.created_at
                }
                for n in self.notes
            ],
            'replay_ids': self.replay_ids,
            'session_ids': self.session_ids
        }


class CaseManager:
    """
    Manages the queue of cases for expert review.
    
    Features:
    - Priority-based queue ordering
    - Case assignment to reviewers
    - Status tracking
    - Statistics
    """
    
    def __init__(self):
        self.cases: Dict[str, Case] = {}
        self.player_cases: Dict[str, List[str]] = {}  # player_id -> case_ids
    
    def create_case(
        self,
        player_id: str,
        tier1_score: float,
        tier2_score: float,
        ai_verdict: str,
        ai_confidence: float,
        ai_reasoning: str,
        top_features: List[tuple] = None
    ) -> Case:
        """
        Create a new case from Tier 2 analysis.
        
        Args:
            player_id: Player being reviewed
            tier1_score: Score from Tier 1
            tier2_score: Score from Tier 2
            ai_verdict: AI's recommended verdict
            ai_confidence: AI's confidence
            ai_reasoning: Explanation from AI
            top_features: Contributing features
            
        Returns:
            New Case object
        """
        case_id = f"case_{uuid.uuid4().hex[:8]}"
        
        # Determine priority based on scores  
        combined = (tier1_score + tier2_score) / 2
        
        if combined >= 0.9:
            priority = CasePriority.CRITICAL
        elif combined >= 0.7:
            priority = CasePriority.HIGH
        elif combined >= 0.5:
            priority = CasePriority.MEDIUM
        else:
            priority = CasePriority.LOW
        
        case = Case(
            case_id=case_id,
            player_id=player_id,
            status=CaseStatus.PENDING,
            priority=priority,
            tier1_score=tier1_score,
            tier2_score=tier2_score,
            combined_score=combined,
            ai_verdict=ai_verdict,
            ai_confidence=ai_confidence,
            ai_reasoning=ai_reasoning,
            top_features=top_features or []
        )
        
        self.cases[case_id] = case
        
        if player_id not in self.player_cases:
            self.player_cases[player_id] = []
        self.player_cases[player_id].append(case_id)
        
        return case
    
    def get_case(self, case_id: str) -> Optional[Case]:
        """Get a case by ID."""
        return self.cases.get(case_id)
    
    def get_player_cases(self, player_id: str) -> List[Case]:
        """Get all cases for a player."""
        case_ids = self.player_cases.get(player_id, [])
        return [self.cases[cid] for cid in case_ids if cid in self.cases]
    
    def get_queue(
        self,
        status: Optional[CaseStatus] = None,
        priority: Optional[CasePriority] = None,
        assigned_to: Optional[str] = None,
        limit: int = 50
    ) -> List[Case]:
        """
        Get cases from the queue.
        
        Args:
            status: Filter by status
            priority: Filter by priority
            assigned_to: Filter by assignee
            limit: Max cases to return
            
        Returns:
            List of cases ordered by priority
        """
        result = []
        
        for case in self.cases.values():
            if status and case.status != status:
                continue
            if priority and case.priority != priority:
                continue
            if assigned_to and case.assigned_to != assigned_to:
                continue
            
            result.append(case)
        
        # Sort by priority (high to low), then by age (oldest first)
        result.sort(key=lambda c: (-c.priority.value, c.created_at))
        
        return result[:limit]
    
    def assign_case(self, case_id: str, reviewer_id: str) -> bool:
        """Assign a case to a reviewer."""
        case = self.cases.get(case_id)
        if not case:
            return False
        
        case.assigned_to = reviewer_id
        case.status = CaseStatus.IN_REVIEW
        case.updated_at = time.time()
        
        return True
    
    def update_status(
        self,
        case_id: str,
        status: CaseStatus,
        reviewer_id: Optional[str] = None,
        notes: str = ""
    ) -> bool:
        """Update case status."""
        case = self.cases.get(case_id)
        if not case:
            return False
        
        case.status = status
        case.updated_at = time.time()
        
        if reviewer_id:
            case.reviewed_by = reviewer_id
        
        if notes:
            case.human_notes = notes
        
        # Set final verdict based on status
        if status == CaseStatus.CLEARED:
            case.final_verdict = "innocent"
        elif status == CaseStatus.BANNED:
            case.final_verdict = "guilty"
        elif status == CaseStatus.MONITORING:
            case.final_verdict = "monitoring"
        
        return True
    
    def get_statistics(self) -> dict:
        """Get case statistics."""
        total = len(self.cases)
        
        status_counts = {}
        for status in CaseStatus:
            status_counts[status.value] = sum(
                1 for c in self.cases.values() if c.status == status
            )
        
        priority_counts = {}
        for priority in CasePriority:
            priority_counts[priority.name.lower()] = sum(
                1 for c in self.cases.values() if c.priority == priority
            )
        
        # Calculate average resolution time for resolved cases
        resolved = [
            c for c in self.cases.values()
            if c.status in (CaseStatus.CLEARED, CaseStatus.BANNED)
        ]
        
        if resolved:
            avg_resolution_time = sum(
                c.updated_at - c.created_at for c in resolved
            ) / len(resolved)
        else:
            avg_resolution_time = 0
        
        # AI accuracy (if we have resolved cases)
        if resolved:
            ai_correct = sum(
                1 for c in resolved
                if (c.ai_verdict == 'ban' and c.status == CaseStatus.BANNED) or
                   (c.ai_verdict in ('clear', 'monitor') and c.status == CaseStatus.CLEARED)
            )
            ai_accuracy = ai_correct / len(resolved)
        else:
            ai_accuracy = 0
        
        return {
            'total_cases': total,
            'status_counts': status_counts,
            'priority_counts': priority_counts,
            'pending_count': status_counts.get('pending', 0),
            'in_review_count': status_counts.get('in_review', 0),
            'avg_resolution_time_seconds': avg_resolution_time,
            'ai_accuracy': ai_accuracy,
            'unique_players': len(self.player_cases)
        }
    
    def export_cases(self, status: Optional[CaseStatus] = None) -> List[dict]:
        """Export cases as dictionaries."""
        cases = self.get_queue(status=status, limit=10000)
        return [c.to_dict() for c in cases]
    
    def get_case_for_api(self, case_id: str) -> Optional[dict]:
        """Get case formatted for API response."""
        case = self.get_case(case_id)
        if not case:
            return None
        
        return {
            **case.to_dict(),
            'created_at_formatted': datetime.fromtimestamp(case.created_at).isoformat(),
            'updated_at_formatted': datetime.fromtimestamp(case.updated_at).isoformat(),
            'age_seconds': time.time() - case.created_at,
            'priority_name': case.priority.name
        }


# Global instance for the server
case_manager = CaseManager()
