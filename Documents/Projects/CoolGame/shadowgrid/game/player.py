"""
ShadowGrid Player Module

Player state, movement, and feature tracking hooks.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Tuple, List, Optional, Deque
from collections import deque
import math

from .constants import (
    Direction, DIRECTION_VECTORS,
    PlayerConfig, DEFAULT_PLAYER_CONFIG,
    TileType
)
from .world import Grid


@dataclass
class MovementRecord:
    """Record of a single movement for feature extraction."""
    tick: int
    timestamp: float
    direction: Direction
    from_pos: Tuple[int, int]
    to_pos: Tuple[int, int]
    velocity: Tuple[float, float]  # Tiles per second
    was_valid: bool


@dataclass
class PlayerStats:
    """Cumulative player statistics for anti-cheat."""
    total_moves: int = 0
    invalid_moves: int = 0
    crystals_collected: int = 0
    lava_touches: int = 0
    deaths: int = 0  # Added missing field
    distance_traveled: float = 0.0
    start_time: float = field(default_factory=time.time)
    
    # Temporal tracking
    move_timestamps: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    movement_history: Deque[MovementRecord] = field(default_factory=lambda: deque(maxlen=500))
    
    # Position history for heatmap
    position_history: List[Tuple[int, int]] = field(default_factory=list)
    
    @property
    def session_duration(self) -> float:
        """Get current session duration in seconds."""
        return time.time() - self.start_time
    
    @property
    def moves_per_second(self) -> float:
        """Calculate average moves per second."""
        if self.session_duration > 0:
            return self.total_moves / self.session_duration
        return 0.0
    
    @property
    def invalid_move_ratio(self) -> float:
        """Calculate ratio of invalid moves."""
        if self.total_moves > 0:
            return self.invalid_moves / self.total_moves
        return 0.0
    
    def record_move(self, record: MovementRecord) -> None:
        """Record a movement for analysis."""
        self.total_moves += 1
        if not record.was_valid:
            self.invalid_moves += 1
        else:
            dx = record.to_pos[0] - record.from_pos[0]
            dy = record.to_pos[1] - record.from_pos[1]
            self.distance_traveled += math.sqrt(dx * dx + dy * dy)
        
        self.move_timestamps.append(record.timestamp)
        self.movement_history.append(record)
        self.position_history.append(record.to_pos)
    
    def get_recent_velocity_stats(self, window: int = 10) -> dict:
        """Get velocity statistics from recent movements."""
        recent = list(self.movement_history)[-window:]
        if not recent:
            return {'avg': 0.0, 'std': 0.0, 'max': 0.0}
        
        velocities = [
            math.sqrt(r.velocity[0]**2 + r.velocity[1]**2)
            for r in recent
        ]
        
        avg = sum(velocities) / len(velocities)
        variance = sum((v - avg)**2 for v in velocities) / len(velocities)
        
        return {
            'avg': avg,
            'std': math.sqrt(variance),
            'max': max(velocities)
        }


@dataclass
class Player:
    """
    Player entity with state and movement validation.
    
    Tracks all movements for anti-cheat feature extraction.
    """
    player_id: str
    x: int = 0
    y: int = 0
    health: int = 100
    score: int = 0
    alive: bool = True
    
    config: PlayerConfig = field(default_factory=lambda: DEFAULT_PLAYER_CONFIG)
    stats: PlayerStats = field(default_factory=PlayerStats)
    
    # Current tick (synchronized with server)
    current_tick: int = 0
    last_move_time: float = field(default_factory=time.time)
    
    def spawn(self, grid: Grid) -> None:
        """Spawn player at configured or random safe position (no lava)."""
        import random
        
        if self.config.starting_position:
            self.x, self.y = self.config.starting_position
            return
        
        # Collect all safe tiles for random spawn
        safe_tiles = []
        
        for y in range(grid.height):
            for x in range(grid.width):
                tile = grid.get_tile(x, y)
                if tile and tile.tile_type not in (TileType.LAVA, TileType.WALL):
                    safe_tiles.append((x, y))
        
        if safe_tiles:
            # Random spawn position for variety
            self.x, self.y = random.choice(safe_tiles)
        else:
            # Absolute fallback - should never happen with valid grid
            self.x, self.y = 1, 1
    
    def move(
        self,
        direction: Direction,
        grid: Grid,
        tick: int,
        timestamp: float = None
    ) -> Tuple[bool, str]:
        """
        Attempt to move in a direction.
        
        Returns:
            (success, message) tuple
        """
        current_time = time.time()
        from_pos = (self.x, self.y)
        
        # Calculate target position
        dx, dy = DIRECTION_VECTORS[direction]
        new_x = self.x + dx
        new_y = self.y + dy
        
        # Validate bounds
        if not (0 <= new_x < grid.width and 0 <= new_y < grid.height):
            self._record_invalid_move(direction, from_pos, tick, timestamp or current_time)
            return False, "Out of bounds"
        
        # Get target tile
        target_tile = grid.get_tile(new_x, new_y)
        if target_tile is None:
            self._record_invalid_move(direction, from_pos, tick, timestamp or current_time)
            return False, "Invalid tile"
        
        # Check walkability
        if target_tile.tile_type == TileType.WALL:
            self._record_invalid_move(direction, from_pos, tick, timestamp or current_time)
            return False, "Cannot walk through walls"
        
        # Calculate velocity for feature tracking
        time_delta = current_time - self.last_move_time
        if time_delta > 0:
            velocity = (dx / time_delta, dy / time_delta)
        else:
            velocity = (0.0, 0.0)
        
        # Execute move
        old_x, old_y = self.x, self.y
        self.x, self.y = new_x, new_y
        self.current_tick = tick
        
        # Handle tile effects
        message = "Moved successfully"
        
        if target_tile.tile_type == TileType.LAVA:
            self.health -= self.config.lava_damage
            self.stats.lava_touches += 1
            message = f"Stepped on lava! -{self.config.lava_damage} HP"
            if self.health <= 0:
                self.alive = False
                self.stats.deaths += 1
                message = "Killed by lava!"
        
        elif target_tile.tile_type == TileType.CRYSTAL:
            if grid.collect_crystal(new_x, new_y):
                self.score += self.config.crystal_reward
                self.stats.crystals_collected += 1
                message = f"Crystal collected! +{self.config.crystal_reward} points"
        
        elif target_tile.tile_type == TileType.EXIT:
            if grid.crystals_remaining == 0:
                message = "Level complete!"
            else:
                message = f"Exit found! Collect {grid.crystals_remaining} more crystals."
        
        # Apply move cost
        self.score -= self.config.move_cost
        
        # Record valid move
        record = MovementRecord(
            tick=tick,
            timestamp=timestamp or current_time,
            direction=direction,
            from_pos=from_pos,
            to_pos=(new_x, new_y),
            velocity=velocity,
            was_valid=True
        )
        self.stats.record_move(record)
        self.last_move_time = current_time
        
        return True, message
    
    def _record_invalid_move(
        self,
        direction: Direction,
        from_pos: Tuple[int, int],
        tick: int,
        timestamp: float
    ) -> None:
        """Record an invalid movement attempt."""
        record = MovementRecord(
            tick=tick,
            timestamp=timestamp,
            direction=direction,
            from_pos=from_pos,
            to_pos=from_pos,  # Didn't move
            velocity=(0.0, 0.0),
            was_valid=False
        )
        self.stats.record_move(record)
    
    def get_visible_tiles(
        self,
        grid: Grid
    ) -> List[List[int]]:
        """Get player's visible portion of the grid (3x3 by default)."""
        return grid.get_visible_state(
            self.x, self.y,
            self.config.visibility_radius
        )
    
    def get_state(self) -> dict:
        """Get serializable player state for network sync."""
        return {
            'player_id': self.player_id,
            'x': self.x,
            'y': self.y,
            'health': self.health,
            'score': self.score,
            'alive': self.alive,
            'tick': self.current_tick
        }
    
    def apply_state(self, state: dict) -> None:
        """Apply state from server (for client sync)."""
        self.x = state['x']
        self.y = state['y']
        self.health = state['health']
        self.score = state['score']
        self.alive = state['alive']
        self.current_tick = state['tick']
    
    def respawn(self, grid: Grid) -> None:
        """Respawn player after death."""
        self.health = self.config.max_health
        self.alive = True
        self.spawn(grid)
