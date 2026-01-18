"""
ShadowGrid Player Repository

CRUD operations for player data and history.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Player, PlayerStatus


class PlayerRepository:
    """
    Repository for player database operations.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, player_id: str) -> Optional[Player]:
        """Get player by ID."""
        result = await self.session.execute(
            select(Player).where(Player.player_id == player_id)
        )
        return result.scalar_one_or_none()
    
    async def get_or_create(self, player_id: str) -> Player:
        """Get existing player or create new one."""
        player = await self.get_by_id(player_id)
        if not player:
            player = Player(player_id=player_id)
            self.session.add(player)
            await self.session.flush()
        return player
    
    async def create(self, player_id: str) -> Player:
        """Create new player."""
        player = Player(player_id=player_id)
        self.session.add(player)
        await self.session.flush()
        return player
    
    async def update_last_seen(self, player_id: str) -> None:
        """Update player's last seen timestamp."""
        await self.session.execute(
            update(Player)
            .where(Player.player_id == player_id)
            .values(last_seen=datetime.utcnow())
        )
    
    async def update_session_stats(
        self,
        player_id: str,
        session_duration: float,
        moves: int,
        crystals: int,
        deaths: int
    ) -> None:
        """Update player aggregate stats after session ends."""
        player = await self.get_by_id(player_id)
        if player:
            player.total_sessions += 1
            player.total_playtime_seconds += session_duration
            player.total_moves += moves
            player.total_crystals += crystals
            player.total_deaths += deaths
            await self.session.flush()
    
    async def update_detection_stats(
        self,
        player_id: str,
        tier1_score: float,
        tier2_score: float,
        was_flagged: bool,
        was_banned: bool = False
    ) -> None:
        """Update player detection statistics."""
        player = await self.get_by_id(player_id)
        if player:
            # Update running averages
            n = player.total_sessions
            if n > 0:
                player.avg_tier1_score = (
                    (player.avg_tier1_score * (n - 1) + tier1_score) / n
                )
                player.avg_tier2_score = (
                    (player.avg_tier2_score * (n - 1) + tier2_score) / n
                )
            
            # Track max score
            combined = (tier1_score + tier2_score) / 2
            if combined > player.max_detection_score:
                player.max_detection_score = combined
            
            if was_flagged:
                player.total_flags += 1
            if was_banned:
                player.total_bans += 1
            
            await self.session.flush()
    
    async def update_violation_counts(
        self,
        player_id: str,
        speed_violations: int = 0,
        fog_violations: int = 0
    ) -> None:
        """Update violation counts."""
        player = await self.get_by_id(player_id)
        if player:
            player.speed_violation_count += speed_violations
            player.fog_violation_count += fog_violations
            await self.session.flush()
    
    async def update_trust_score(
        self,
        player_id: str,
        delta: float
    ) -> None:
        """Adjust player trust score."""
        player = await self.get_by_id(player_id)
        if player:
            player.trust_score = max(0.0, min(1.0, player.trust_score + delta))
            await self.session.flush()
    
    async def set_status(
        self,
        player_id: str,
        status: PlayerStatus,
        ban_expires: Optional[datetime] = None
    ) -> None:
        """Set player account status."""
        player = await self.get_by_id(player_id)
        if player:
            player.status = status
            player.ban_expires = ban_expires
            await self.session.flush()
    
    async def get_flagged_players(
        self,
        min_flags: int = 1,
        limit: int = 100
    ) -> List[Player]:
        """Get players with flags for review."""
        result = await self.session.execute(
            select(Player)
            .where(Player.total_flags >= min_flags)
            .order_by(Player.total_flags.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_history_features(self, player_id: str) -> Optional[dict]:
        """Get player history as Tier 2 feature dict."""
        player = await self.get_by_id(player_id)
        if player:
            return player.to_history_dict()
        return None
