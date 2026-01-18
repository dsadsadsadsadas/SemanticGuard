"""
ShadowGrid Session Repository

CRUD operations for game sessions and replay data.
"""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Session


class SessionRepository:
    """
    Repository for session database operations.
    """
    
    def __init__(self, session: AsyncSession):
        self.db_session = session
    
    async def create(self, player_id: str) -> Session:
        """Create new game session."""
        session = Session(
            session_id=f"sess_{uuid.uuid4().hex[:16]}",
            player_id=player_id
        )
        self.db_session.add(session)
        await self.db_session.flush()
        return session
    
    async def get_by_id(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        result = await self.db_session.execute(
            select(Session).where(Session.session_id == session_id)
        )
        return result.scalar_one_or_none()
    
    async def end_session(
        self,
        session_id: str,
        crystals: int,
        deaths: int,
        moves: int,
        score: int
    ) -> None:
        """End session and record final stats."""
        session = await self.get_by_id(session_id)
        if session:
            session.ended_at = datetime.utcnow()
            session.duration_seconds = (
                session.ended_at - session.started_at
            ).total_seconds()
            session.crystals_collected = crystals
            session.deaths = deaths
            session.total_moves = moves
            session.score = score
            await self.db_session.flush()
    
    async def update_detection(
        self,
        session_id: str,
        tier1_score: float,
        tier2_score: float,
        combined_score: float,
        was_flagged: bool,
        verdict: Optional[str] = None

    ) -> None:
        """Update session detection results."""
        session = await self.get_by_id(session_id)
        if session:
            session.tier1_score = tier1_score
            session.tier2_score = tier2_score
            session.combined_score = combined_score
            session.was_flagged = was_flagged
            session.verdict = verdict
            await self.db_session.flush()
    
    async def save_features(
        self,
        session_id: str,
        features: dict
    ) -> None:
        """Save feature snapshot for session."""
        session = await self.get_by_id(session_id)
        if session:
            session.features = features
            await self.db_session.flush()
    
    async def save_replay(
        self,
        session_id: str,
        replay_data: list
    ) -> None:
        """Save replay data for session."""
        session = await self.get_by_id(session_id)
        if session:
            session.replay_data = replay_data
            await self.db_session.flush()
    
    async def get_player_sessions(
        self,
        player_id: str,
        limit: int = 10
    ) -> List[Session]:
        """Get recent sessions for a player."""
        result = await self.db_session.execute(
            select(Session)
            .where(Session.player_id == player_id)
            .order_by(Session.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_flagged_sessions(
        self,
        limit: int = 100
    ) -> List[Session]:
        """Get sessions that were flagged."""
        result = await self.db_session.execute(
            select(Session)
            .where(Session.was_flagged == True)
            .order_by(Session.combined_score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_recent_sessions(
        self,
        hours: int = 24,
        limit: int = 100
    ) -> List[Session]:
        """Get sessions from last N hours."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        result = await self.db_session.execute(
            select(Session)
            .where(Session.started_at >= cutoff)
            .order_by(Session.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
