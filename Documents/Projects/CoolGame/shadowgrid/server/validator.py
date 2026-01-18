"""
ShadowGrid Input Validator

Advanced input validation with cheat detection scoring.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import deque

from ..game.constants import Direction, DIRECTION_VECTORS
from ..game.lockstep import PlayerInput, InputType, ValidationResult


@dataclass
class PlayerValidationState:
    """Tracks validation state for a single player."""
    player_id: str
    
    # Movement tracking
    last_position: Tuple[int, int] = (0, 0)
    last_move_time: float = 0.0
    move_timestamps: deque = field(default_factory=lambda: deque(maxlen=50))
    
    # Violation counters
    speed_violations: int = 0
    impossible_moves: int = 0
    state_mismatches: int = 0
    timing_anomalies: int = 0
    
    # Suspicion score (0-100)
    suspicion_score: float = 0.0
    
    def add_violation(self, severity: float, reason: str) -> None:
        """Add a violation and update suspicion score."""
        # Exponential decay + new violation
        self.suspicion_score = min(100, self.suspicion_score * 0.95 + severity)
    
    def decay_suspicion(self) -> None:
        """Apply time-based decay to suspicion score."""
        self.suspicion_score *= 0.99


class InputValidator:
    """
    Validates player inputs against game rules and physics.
    
    Tracks patterns that indicate cheating:
    - Speed hacks (moving too fast)
    - Teleportation (impossible position changes)
    - State manipulation (hash mismatches)
    - Timing anomalies (superhuman reaction times)
    """
    
    # Thresholds
    MIN_MOVE_INTERVAL_MS: float = 40  # Max ~25 moves/second
    MAX_TELEPORT_DISTANCE: int = 2     # Max tiles per input
    SUSPICION_THRESHOLD: float = 50.0  # Flag for Tier 2 review
    
    def __init__(self):
        self.player_states: Dict[str, PlayerValidationState] = {}
        self.flagged_players: List[str] = []
    
    def get_or_create_state(self, player_id: str) -> PlayerValidationState:
        """Get or create validation state for a player."""
        if player_id not in self.player_states:
            self.player_states[player_id] = PlayerValidationState(player_id=player_id)
        return self.player_states[player_id]
    
    def validate_input(
        self,
        input: PlayerInput,
        current_position: Tuple[int, int],
        game_tick: int
    ) -> ValidationResult:
        """
        Validate a player input.
        
        Returns ValidationResult with severity level.
        """
        state = self.get_or_create_state(input.player_id)
        current_time = time.time()
        
        # Check 1: Timing (too fast input rate)
        if state.move_timestamps:
            last_time = state.move_timestamps[-1]
            interval_ms = (current_time - last_time) * 1000
            
            if interval_ms < self.MIN_MOVE_INTERVAL_MS:
                state.timing_anomalies += 1
                state.add_violation(5.0, "Input rate too high")
                
                if state.timing_anomalies > 10:
                    return ValidationResult.suspicious(
                        f"Persistent timing anomaly: {interval_ms:.1f}ms intervals"
                    )
        
        # Check 2: Movement physics
        if input.input_type == InputType.MOVE:
            dx, dy = DIRECTION_VECTORS[input.direction]
            expected_pos = (current_position[0] + dx, current_position[1] + dy)
            
            # Track for distance checking
            if state.last_position != (0, 0):
                distance = abs(current_position[0] - state.last_position[0]) + \
                           abs(current_position[1] - state.last_position[1])
                
                if distance > self.MAX_TELEPORT_DISTANCE:
                    state.impossible_moves += 1
                    state.add_violation(20.0, f"Teleport detected: {distance} tiles")
                    
                    return ValidationResult.cheat(
                        f"Impossible position change: {distance} tiles"
                    )
        
        # Update state
        state.move_timestamps.append(current_time)
        state.last_position = current_position
        state.last_move_time = current_time
        state.decay_suspicion()
        
        # Check if player should be flagged
        if state.suspicion_score >= self.SUSPICION_THRESHOLD:
            if input.player_id not in self.flagged_players:
                self.flagged_players.append(input.player_id)
                
                # Create case in database (async, fire-and-forget)
                import asyncio
                asyncio.create_task(self._create_case(
                    player_id=input.player_id,
                    session_id=None,
                    tier1_score=state.suspicion_score / 100.0,
                    reason=f"Flagged for Tier 2 review: timing_anomalies={state.timing_anomalies}, impossible_moves={state.impossible_moves}"
                ))
                
                return ValidationResult(
                    valid=True,
                    reason=f"Player flagged for Tier 2 review: score={state.suspicion_score:.1f}",
                    severity=2
                )
        
        return ValidationResult.ok()
    
    async def _create_case(
        self,
        player_id: str,
        session_id: str | None,
        tier1_score: float,
        reason: str
    ) -> None:
        """Create a case in the database for flagged player."""
        import uuid
        from datetime import datetime
        try:
            from ..database import db_manager, Case, CaseStatus, CasePriority
            
            priority = CasePriority.HIGH if tier1_score > 0.8 else (
                CasePriority.MEDIUM if tier1_score > 0.5 else CasePriority.LOW
            )
            
            async with db_manager.session_factory() as session:
                case = Case(
                    case_id=f"case_{uuid.uuid4().hex[:8]}",
                    player_id=player_id,
                    session_id=session_id,
                    status=CaseStatus.PENDING,
                    priority=priority,
                    tier1_score=tier1_score,
                    tier2_score=0.0,
                    ai_confidence=tier1_score,
                    ai_reasoning=reason
                )
                session.add(case)
                await session.commit()
                print(f"📋 Created case {case.case_id} for {player_id} (score: {tier1_score:.2f})")
        except Exception as e:
            print(f"Error creating case: {e}")
    
    def validate_state_hash(
        self,
        player_id: str,
        client_hash: str,
        server_hash: str
    ) -> ValidationResult:
        """Validate client state hash against server."""
        if client_hash != server_hash:
            state = self.get_or_create_state(player_id)
            state.state_mismatches += 1
            state.add_violation(30.0, "State hash mismatch")
            
            if state.state_mismatches > 3:
                return ValidationResult.cheat(
                    f"Persistent state mismatch: {state.state_mismatches} times"
                )
            
            return ValidationResult.suspicious("State hash mismatch")
        
        return ValidationResult.ok()
    
    def get_flagged_players(self) -> List[Tuple[str, float]]:
        """Get list of flagged players with their suspicion scores."""
        return [
            (pid, self.player_states[pid].suspicion_score)
            for pid in self.flagged_players
            if pid in self.player_states
        ]
    
    def get_player_stats(self, player_id: str) -> Optional[dict]:
        """Get validation statistics for a player."""
        state = self.player_states.get(player_id)
        if not state:
            return None
        
        return {
            'player_id': player_id,
            'suspicion_score': state.suspicion_score,
            'speed_violations': state.speed_violations,
            'impossible_moves': state.impossible_moves,
            'state_mismatches': state.state_mismatches,
            'timing_anomalies': state.timing_anomalies,
            'is_flagged': player_id in self.flagged_players
        }
    
    def clear_player(self, player_id: str) -> None:
        """Clear validation state for a player."""
        self.player_states.pop(player_id, None)
        if player_id in self.flagged_players:
            self.flagged_players.remove(player_id)
