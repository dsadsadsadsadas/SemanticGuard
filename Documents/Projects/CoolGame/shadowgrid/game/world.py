"""
ShadowGrid World Module

The game grid with tiles, visibility system, and procedural generation.
"""

from __future__ import annotations
import random
import hashlib
from dataclasses import dataclass, field
from typing import List, Tuple, Set, Optional
import numpy as np

from .constants import (
    TileType, Direction, DIRECTION_VECTORS,
    GridConfig, DEFAULT_GRID_CONFIG
)


@dataclass
class Tile:
    """A single tile in the grid."""
    tile_type: TileType = TileType.EMPTY
    visited: bool = False
    
    def is_walkable(self) -> bool:
        """Check if player can walk on this tile."""
        return self.tile_type not in (TileType.WALL, TileType.LAVA)
    
    def is_deadly(self) -> bool:
        """Check if this tile damages the player."""
        return self.tile_type == TileType.LAVA
    
    def is_collectible(self) -> bool:
        """Check if this tile has something to collect."""
        return self.tile_type == TileType.CRYSTAL


@dataclass
class Grid:
    """
    The game world grid.
    
    Maintains full state on the server side.
    Provides visibility-masked views for clients.
    """
    width: int
    height: int
    tiles: List[List[Tile]] = field(default_factory=list)
    crystals_remaining: int = 0
    _rng: random.Random = field(default_factory=random.Random, repr=False)
    
    def __post_init__(self):
        """Initialize empty grid if tiles not provided."""
        if not self.tiles:
            self.tiles = [
                [Tile() for _ in range(self.width)]
                for _ in range(self.height)
            ]
    
    @classmethod
    def generate(cls, config: GridConfig = DEFAULT_GRID_CONFIG) -> Grid:
        """
        Generate a new grid with procedural content.
        
        Guarantees:
        - Player spawn is on a safe tile
        - Exit is reachable from spawn
        - At least one crystal is reachable
        """
        rng = random.Random(config.seed)
        
        grid = cls(width=config.width, height=config.height)
        grid._rng = rng
        
        # Phase 1: Generate walls (maze-like structure)
        grid._generate_walls(config.wall_density)
        
        # Phase 2: Generate lava pools
        grid._generate_lava(config.lava_density)
        
        # Phase 3: Place crystals
        grid._place_crystals(config.crystal_count)
        
        # Phase 4: Place exit
        grid._place_exit()
        
        # Phase 5: Validate and ensure solvability
        grid._ensure_solvability()
        
        return grid
    
    def _generate_walls(self, density: float) -> None:
        """Generate wall tiles with given density."""
        total_tiles = self.width * self.height
        wall_count = int(total_tiles * density)
        
        positions = [
            (x, y) 
            for x in range(self.width) 
            for y in range(self.height)
            # Keep borders open for navigation
            if 1 <= x < self.width - 1 and 1 <= y < self.height - 1
        ]
        
        self._rng.shuffle(positions)
        
        for x, y in positions[:wall_count]:
            self.tiles[y][x].tile_type = TileType.WALL
    
    def _generate_lava(self, density: float) -> None:
        """Generate lava pools with organic shapes."""
        total_tiles = self.width * self.height
        lava_count = int(total_tiles * density)
        
        # Find empty tiles
        empty_positions = [
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if self.tiles[y][x].tile_type == TileType.EMPTY
        ]
        
        self._rng.shuffle(empty_positions)
        
        placed = 0
        for x, y in empty_positions:
            if placed >= lava_count:
                break
            
            # Create small lava pool (1-3 tiles)
            pool_size = self._rng.randint(1, 3)
            pool_tiles = [(x, y)]
            
            for _ in range(pool_size - 1):
                # Expand to adjacent tile
                px, py = self._rng.choice(pool_tiles)
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nx, ny = px + dx, py + dy
                    if (0 <= nx < self.width and 0 <= ny < self.height and
                        self.tiles[ny][nx].tile_type == TileType.EMPTY and
                        (nx, ny) not in pool_tiles):
                        pool_tiles.append((nx, ny))
                        break
            
            for px, py in pool_tiles:
                self.tiles[py][px].tile_type = TileType.LAVA
                placed += 1
    
    def _place_crystals(self, count: int) -> None:
        """Place crystals on empty tiles."""
        empty_positions = [
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if self.tiles[y][x].tile_type == TileType.EMPTY
        ]
        
        self._rng.shuffle(empty_positions)
        
        for x, y in empty_positions[:count]:
            self.tiles[y][x].tile_type = TileType.CRYSTAL
            self.crystals_remaining += 1
    
    def _place_exit(self) -> None:
        """Place exit tile in a corner area."""
        # Prefer bottom-right quadrant for exit
        candidates = [
            (x, y)
            for x in range(self.width * 2 // 3, self.width)
            for y in range(self.height * 2 // 3, self.height)
            if self.tiles[y][x].tile_type == TileType.EMPTY
        ]
        
        if candidates:
            x, y = self._rng.choice(candidates)
            self.tiles[y][x].tile_type = TileType.EXIT
        else:
            # Fallback: any empty tile
            for y in range(self.height - 1, -1, -1):
                for x in range(self.width - 1, -1, -1):
                    if self.tiles[y][x].tile_type == TileType.EMPTY:
                        self.tiles[y][x].tile_type = TileType.EXIT
                        return
    
    def _ensure_solvability(self) -> None:
        """Ensure the grid is solvable using flood fill."""
        # Find spawn area (top-left quadrant)
        spawn = self._find_safe_spawn()
        if spawn is None:
            # Create a safe spawn
            self.tiles[1][1].tile_type = TileType.EMPTY
            spawn = (1, 1)
        
        # BFS to check reachability
        reachable = self._flood_fill(spawn)
        
        # Check if exit is reachable
        exit_pos = self._find_exit()
        if exit_pos and exit_pos not in reachable:
            # Carve path to exit
            self._carve_path(spawn, exit_pos)
        
        # Check if at least one crystal is reachable
        crystal_found = False
        for x, y in reachable:
            if self.tiles[y][x].tile_type == TileType.CRYSTAL:
                crystal_found = True
                break
        
        if not crystal_found and self.crystals_remaining > 0:
            # Find nearest crystal and carve path
            crystals = [
                (x, y)
                for x in range(self.width)
                for y in range(self.height)
                if self.tiles[y][x].tile_type == TileType.CRYSTAL
            ]
            if crystals:
                target = min(crystals, key=lambda p: abs(p[0] - spawn[0]) + abs(p[1] - spawn[1]))
                self._carve_path(spawn, target)
    
    def _find_safe_spawn(self) -> Optional[Tuple[int, int]]:
        """Find a safe spawn position in the top-left area."""
        for y in range(min(5, self.height)):
            for x in range(min(5, self.width)):
                if self.tiles[y][x].tile_type == TileType.EMPTY:
                    return (x, y)
        return None
    
    def _find_exit(self) -> Optional[Tuple[int, int]]:
        """Find the exit tile position."""
        for y in range(self.height):
            for x in range(self.width):
                if self.tiles[y][x].tile_type == TileType.EXIT:
                    return (x, y)
        return None
    
    def _flood_fill(self, start: Tuple[int, int]) -> Set[Tuple[int, int]]:
        """BFS flood fill to find reachable tiles."""
        reachable = set()
        queue = [start]
        
        while queue:
            x, y = queue.pop(0)
            if (x, y) in reachable:
                continue
            if not (0 <= x < self.width and 0 <= y < self.height):
                continue
            if self.tiles[y][x].tile_type in (TileType.WALL, TileType.LAVA):
                continue
            
            reachable.add((x, y))
            
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                queue.append((x + dx, y + dy))
        
        return reachable
    
    def _carve_path(self, start: Tuple[int, int], end: Tuple[int, int]) -> None:
        """Carve a walkable path between two points."""
        x, y = start
        ex, ey = end
        
        while (x, y) != (ex, ey):
            if x < ex:
                x += 1
            elif x > ex:
                x -= 1
            elif y < ey:
                y += 1
            elif y > ey:
                y -= 1
            
            if self.tiles[y][x].tile_type in (TileType.WALL, TileType.LAVA):
                self.tiles[y][x].tile_type = TileType.EMPTY
    
    def get_tile(self, x: int, y: int) -> Optional[Tile]:
        """Get tile at position, or None if out of bounds."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.tiles[y][x]
        return None
    
    def get_visibility_mask(
        self, 
        player_x: int, 
        player_y: int, 
        radius: int = 1
    ) -> np.ndarray:
        """
        Generate visibility mask for POMDP.
        
        Returns a 2D numpy array where:
        - 1 = visible
        - 0 = not visible (in fog)
        """
        mask = np.zeros((self.height, self.width), dtype=np.int8)
        
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = player_x + dx, player_y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    mask[ny][nx] = 1
        
        return mask
    
    def get_visible_state(
        self,
        player_x: int,
        player_y: int,
        radius: int = 1
    ) -> List[List[int]]:
        """
        Get partial observation for client.
        
        Returns a 2D array of tile types, with -1 for non-visible tiles.
        """
        mask = self.get_visibility_mask(player_x, player_y, radius)
        
        result = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                if mask[y][x]:
                    row.append(int(self.tiles[y][x].tile_type))
                else:
                    row.append(-1)  # Fog
            result.append(row)
        
        return result
    
    def get_full_state(self) -> List[List[int]]:
        """Get complete grid state (server-side only)."""
        return [
            [int(tile.tile_type) for tile in row]
            for row in self.tiles
        ]
    
    def collect_crystal(self, x: int, y: int) -> bool:
        """Attempt to collect crystal at position."""
        tile = self.get_tile(x, y)
        if tile and tile.tile_type == TileType.CRYSTAL:
            tile.tile_type = TileType.EMPTY
            self.crystals_remaining -= 1
            return True
        return False
    
    def compute_hash(self) -> str:
        """Compute deterministic hash of grid state."""
        state_bytes = bytes([
            int(tile.tile_type)
            for row in self.tiles
            for tile in row
        ])
        return hashlib.sha256(state_bytes).hexdigest()[:16]
    
    def to_numpy(self) -> np.ndarray:
        """Convert grid to numpy array for ML processing."""
        return np.array([
            [int(tile.tile_type) for tile in row]
            for row in self.tiles
        ], dtype=np.int8)
