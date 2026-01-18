"""
ShadowGrid Game Constants

All configurable game parameters and enums.
"""

from enum import IntEnum, auto
from dataclasses import dataclass
from typing import Tuple


# =============================================================================
# TILE TYPES
# =============================================================================

class TileType(IntEnum):
    """Types of tiles in the grid world."""
    EMPTY = 0
    LAVA = 1
    CRYSTAL = 2
    WALL = 3
    EXIT = 4


# =============================================================================
# MOVEMENT DIRECTIONS
# =============================================================================

class Direction(IntEnum):
    """Cardinal movement directions."""
    NONE = 0
    UP = 1
    DOWN = 2
    LEFT = 3
    RIGHT = 4


# Direction vectors for movement
DIRECTION_VECTORS: dict[Direction, Tuple[int, int]] = {
    Direction.NONE: (0, 0),
    Direction.UP: (0, -1),
    Direction.DOWN: (0, 1),
    Direction.LEFT: (-1, 0),
    Direction.RIGHT: (1, 0),
}


# =============================================================================
# GRID CONFIGURATION
# =============================================================================

@dataclass(frozen=True)
class GridConfig:
    """Configuration for the game grid."""
    width: int = 40          # Doubled size (4x area)
    height: int = 40
    lava_density: float = 0.15       # 15% of tiles are lava
    crystal_count: int = 30          # More crystals for larger map
    wall_density: float = 0.10       # 10% of tiles are walls
    seed: int | None = None          # Random seed for reproducibility


DEFAULT_GRID_CONFIG = GridConfig()


# =============================================================================
# PLAYER CONFIGURATION
# =============================================================================

@dataclass(frozen=True)
class PlayerConfig:
    """Configuration for player mechanics."""
    visibility_radius: int = 1        # 1 = 3x3 vision (radius includes center)
    max_health: int = 100
    lava_damage: int = 50            # Damage per tick on lava
    crystal_reward: int = 100        # Score per crystal
    move_cost: int = 1               # Score cost per move
    starting_position: Tuple[int, int] | None = None  # None = random safe tile


DEFAULT_PLAYER_CONFIG = PlayerConfig()


# =============================================================================
# GAME TICK CONFIGURATION
# =============================================================================

@dataclass(frozen=True)
class TickConfig:
    """Configuration for game timing."""
    tick_rate: int = 20              # Ticks per second
    input_buffer_size: int = 5       # Max buffered inputs
    max_tick_delta: int = 10         # Max ticks client can be behind
    rollback_threshold: int = 3      # Ticks difference to trigger resync


DEFAULT_TICK_CONFIG = TickConfig()


# =============================================================================
# ANTI-CHEAT FEATURE TRACKING
# =============================================================================

@dataclass(frozen=True)
class FeatureTrackingConfig:
    """Configuration for anti-cheat feature extraction."""
    sample_rate: int = 10            # Feature samples per second
    window_size: int = 100           # Rolling window for temporal features
    heatmap_resolution: int = 1      # Heatmap grid resolution (1:1 with game grid)


DEFAULT_FEATURE_CONFIG = FeatureTrackingConfig()


# =============================================================================
# VISUAL CONSTANTS
# =============================================================================

# Tile colors (RGB)
TILE_COLORS: dict[TileType, Tuple[int, int, int]] = {
    TileType.EMPTY: (40, 44, 52),       # Dark gray
    TileType.LAVA: (255, 87, 51),       # Orange-red
    TileType.CRYSTAL: (0, 255, 170),    # Cyan
    TileType.WALL: (80, 85, 96),        # Medium gray
    TileType.EXIT: (138, 43, 226),      # Purple
}

# Player colors
PLAYER_COLOR: Tuple[int, int, int] = (97, 218, 251)  # Light blue
FOG_COLOR: Tuple[int, int, int] = (20, 22, 28)       # Very dark gray

# Tile size in pixels
TILE_SIZE: int = 32

# UI Colors
UI_BACKGROUND: Tuple[int, int, int] = (30, 33, 40)
UI_TEXT: Tuple[int, int, int] = (200, 204, 212)
UI_ACCENT: Tuple[int, int, int] = (97, 218, 251)
