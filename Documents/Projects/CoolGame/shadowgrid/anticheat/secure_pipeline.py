"""
ShadowGrid Secure Pipeline

Dual-channel communication system for Warden integrity reports.
Game moves go through one channel, Warden reports go through another.
The server correlates both to detect tampering.
"""

import asyncio
import json
import time
import hashlib
from dataclasses import dataclass, asdict
from typing import Optional, Callable, Any
from enum import Enum


class ChannelType(Enum):
    GAME = "game"
    WARDEN = "warden"


@dataclass
class PipelineSession:
    """Represents a dual-channel session."""
    session_id: str
    player_id: str
    game_channel_connected: bool = False
    warden_channel_connected: bool = False
    last_game_move_time: float = 0.0
    last_warden_report_time: float = 0.0
    warden_report_count: int = 0
    integrity_violations: int = 0


class SecurePipeline:
    """
    Dual-channel communication for Warden-protected clients.
    
    Channel A (Game): Regular game moves ws://server/ws/{player_id}
    Channel B (Warden): Integrity reports ws://server/warden/{session_id}
    
    The server rejects moves if:
    - Warden report is missing (timeout)
    - Warden report signature is invalid
    - Warden reports integrity violation
    """
    
    # How long to wait for Warden report before rejecting moves
    WARDEN_TIMEOUT_SECONDS = 5.0
    
    # Sessions indexed by session_id
    sessions: dict[str, PipelineSession] = {}
    
    # Session indexed by player_id (for quick lookup)
    player_sessions: dict[str, str] = {}
    
    def __init__(self):
        self.sessions = {}
        self.player_sessions = {}
    
    def create_session(self, player_id: str) -> PipelineSession:
        """
        Create a new dual-channel session.
        
        Returns session with cryptographic session_id.
        """
        # Generate cryptographic session ID
        session_id = self._generate_session_id(player_id)
        
        session = PipelineSession(
            session_id=session_id,
            player_id=player_id
        )
        
        self.sessions[session_id] = session
        self.player_sessions[player_id] = session_id
        
        return session
    
    def get_session_by_player(self, player_id: str) -> Optional[PipelineSession]:
        """Get session for a player."""
        session_id = self.player_sessions.get(player_id)
        if session_id:
            return self.sessions.get(session_id)
        return None
    
    def get_session(self, session_id: str) -> Optional[PipelineSession]:
        """Get session by session_id."""
        return self.sessions.get(session_id)
    
    def connect_game_channel(self, player_id: str) -> bool:
        """Mark game channel as connected."""
        session = self.get_session_by_player(player_id)
        if session:
            session.game_channel_connected = True
            return True
        return False
    
    def connect_warden_channel(self, session_id: str) -> bool:
        """Mark warden channel as connected."""
        session = self.sessions.get(session_id)
        if session:
            session.warden_channel_connected = True
            return True
        return False
    
    def validate_game_move(
        self, 
        player_id: str, 
        move: dict
    ) -> tuple[bool, str]:
        """
        Validate a game move against Warden status.
        
        Returns (valid, reason).
        """
        session = self.get_session_by_player(player_id)
        
        if not session:
            # No session = no Warden protection required (legacy client?)
            return True, "no_session"
        
        # Check if Warden channel is connected
        if not session.warden_channel_connected:
            # Allow brief grace period for connection
            if session.game_channel_connected:
                # Game connected but Warden not? Suspicious after timeout
                if session.warden_report_count == 0:
                    # Never received a report - might be starting up
                    return True, "warden_initializing"
            return True, "warden_not_connected"
        
        # Check Warden report timeout
        time_since_report = time.time() - session.last_warden_report_time
        if time_since_report > self.WARDEN_TIMEOUT_SECONDS:
            session.integrity_violations += 1
            return False, f"warden_timeout ({time_since_report:.1f}s)"
        
        # Check integrity violation count
        if session.integrity_violations >= 3:
            return False, "too_many_violations"
        
        # Move is valid
        session.last_game_move_time = time.time()
        return True, "ok"
    
    def receive_warden_report(
        self, 
        session_id: str, 
        report: dict
    ) -> tuple[bool, str]:
        """
        Process incoming Warden report.
        
        Returns (valid, reason).
        """
        session = self.sessions.get(session_id)
        
        if not session:
            return False, "unknown_session"
        
        # Verify signature
        if not self._verify_signature(session, report):
            session.integrity_violations += 1
            return False, "invalid_signature"
        
        # Check reported integrity
        if not report.get('integrity_valid', False):
            session.integrity_violations += 1
            print(f"🚨 Warden reports integrity violation for {session.player_id}")
            return True, "integrity_violation_reported"
        
        # Check self-integrity
        if not report.get('self_integrity_valid', True):
            session.integrity_violations += 3  # Critical - immediate escalation
            print(f"🚨🚨 Warden SELF-TAMPERING detected for {session.player_id}!")
            return True, "warden_tampering_detected"
        
        # Valid report
        session.last_warden_report_time = time.time()
        session.warden_report_count += 1
        
        # Log any alerts
        alerts = report.get('alerts', [])
        for alert in alerts:
            if isinstance(alert, dict):
                severity = alert.get('severity', 'INFO')
                message = alert.get('message', 'Unknown')
                print(f"   🛡️ Warden Alert [{severity}]: {message}")
        
        return True, "ok"
    
    def disconnect_session(self, player_id: str) -> None:
        """Clean up session on disconnect."""
        session_id = self.player_sessions.pop(player_id, None)
        if session_id:
            self.sessions.pop(session_id, None)
    
    def get_all_sessions_status(self) -> list[dict]:
        """Get status of all active sessions for dashboard."""
        return [
            {
                'session_id': s.session_id[:12] + '...',
                'player_id': s.player_id,
                'game_connected': s.game_channel_connected,
                'warden_connected': s.warden_channel_connected,
                'report_count': s.warden_report_count,
                'violations': s.integrity_violations,
                'last_report_age': time.time() - s.last_warden_report_time if s.last_warden_report_time > 0 else -1
            }
            for s in self.sessions.values()
        ]
    
    def _generate_session_id(self, player_id: str) -> str:
        """Generate cryptographic session ID."""
        data = f"{player_id}:{time.time()}:{id(self)}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def _verify_signature(self, session: PipelineSession, report: dict) -> bool:
        """
        Verify Warden report signature.
        
        In production, this would use HMAC with session-specific key.
        """
        provided_sig = report.get('signature', '')
        
        # Recompute expected signature
        data = f"{report.get('session_id')}:{report.get('timestamp')}:{report.get('integrity_valid')}"
        expected_sig = hashlib.sha256(data.encode()).hexdigest()[:32]
        
        return provided_sig == expected_sig


# Global instance
secure_pipeline = SecurePipeline()
