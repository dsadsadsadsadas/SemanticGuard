"""
ShadowGrid Cheater Environment

Gymnasium environment for training adversarial cheater agents.
"""

from __future__ import annotations
import numpy as np
from typing import Optional, Tuple, Dict, Any

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:
    import gym
    from gym import spaces

from ..game.world import Grid, GridConfig
from ..game.player import Player
from ..game.constants import (
    TileType, Direction, DIRECTION_VECTORS,
    DEFAULT_PLAYER_CONFIG
)


class CheaterEnv(gym.Env):
    """
    Full-observability environment for training cheater agents.
    
    The cheater has access to:
    - Complete grid state (ESP/Wallhack)
    - Optimal paths to objectives
    - All player positions
    
    The cheater must learn to:
    - Maximize game rewards (collect crystals)
    - Minimize detection by anti-cheat
    
    Observation: Full grid state + player state
    Action: Movement + stealthiness toggle
    Reward: crystals - (detectability_score * lambda)
    """
    
    metadata = {'render_modes': ['human', 'rgb_array']}
    
    def __init__(
        self,
        grid_config: GridConfig = GridConfig(),
        detectability_lambda: float = 0.5,
        max_steps: int = 500,
        detector_callback: Optional[callable] = None
    ):
        super().__init__()
        
        self.grid_config = grid_config
        self.detectability_lambda = detectability_lambda
        self.max_steps = max_steps
        self.detector_callback = detector_callback
        
        # Grid dimensions
        self.width = grid_config.width
        self.height = grid_config.height
        
        # Observation space: Full grid + player state
        # Grid: (height, width, 5) for one-hot tile types
        # Player: (x, y, health, score, step)
        grid_obs_dim = self.height * self.width * 5
        player_obs_dim = 5
        
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(grid_obs_dim + player_obs_dim,),
            dtype=np.float32
        )
        
        # Action space: 5 directions + stealth mode toggle
        # 0: NONE, 1: UP, 2: DOWN, 3: LEFT, 4: RIGHT
        # 5-9: Same but with stealth mode (try to look human)
        self.action_space = spaces.Discrete(10)
        
        # State
        self.grid: Optional[Grid] = None
        self.player: Optional[Player] = None
        self.current_step: int = 0
        self.stealth_mode: bool = False
        
        # Feature tracking for detection
        self.movement_history: list = []
        self.fog_violations: int = 0
        self.optimal_moves: int = 0
        self.total_moves: int = 0
    
    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[dict] = None
    ) -> Tuple[np.ndarray, dict]:
        """Reset the environment."""
        super().reset(seed=seed)
        
        # Generate new grid
        config = GridConfig(
            width=self.width,
            height=self.height,
            seed=seed
        )
        self.grid = Grid.generate(config)
        
        # Create player with full observability
        self.player = Player(
            player_id="cheater",
            config=DEFAULT_PLAYER_CONFIG
        )
        self.player.spawn(self.grid)
        
        # Reset tracking
        self.current_step = 0
        self.movement_history = []
        self.fog_violations = 0
        self.optimal_moves = 0
        self.total_moves = 0
        self.stealth_mode = False
        
        obs = self._get_observation()
        info = self._get_info()
        
        return obs, info
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """Execute one step in the environment."""
        self.current_step += 1
        
        # Parse action
        if action >= 5:
            self.stealth_mode = True
            direction = Direction(action - 5)
        else:
            self.stealth_mode = False
            direction = Direction(action)
        
        # Store pre-move state
        old_score = self.player.score
        old_crystals = self.player.stats.crystals_collected
        old_pos = (self.player.x, self.player.y)
        
        # Execute move
        if direction != Direction.NONE:
            success, message = self.player.move(
                direction,
                self.grid,
                self.current_step
            )
            
            if success:
                self.total_moves += 1
                self._track_movement(old_pos, (self.player.x, self.player.y))
        
        # Calculate game reward
        crystals_gained = self.player.stats.crystals_collected - old_crystals
        game_reward = crystals_gained * 100  # Big reward for crystals
        
        # Add small living reward
        if self.player.alive:
            game_reward += 0.1
        
        # Calculate detectability penalty
        detectability = self._calculate_detectability()
        detection_penalty = detectability * self.detectability_lambda
        
        # Combined reward
        reward = game_reward - detection_penalty
        
        # Check termination
        terminated = False
        truncated = False
        
        if not self.player.alive:
            terminated = True
            reward -= 50  # Death penalty
        
        if self.grid.crystals_remaining == 0:
            terminated = True
            reward += 500  # Win bonus
        
        if self.current_step >= self.max_steps:
            truncated = True
        
        obs = self._get_observation()
        info = self._get_info()
        info['detectability'] = detectability
        info['game_reward'] = game_reward
        info['detection_penalty'] = detection_penalty
        
        return obs, reward, terminated, truncated, info
    
    def _get_observation(self) -> np.ndarray:
        """Get full observation (cheater has full map access)."""
        # One-hot encode grid
        grid_obs = np.zeros(
            (self.height, self.width, 5),
            dtype=np.float32
        )
        
        for y in range(self.height):
            for x in range(self.width):
                tile = self.grid.get_tile(x, y)
                if tile:
                    tile_type = int(tile.tile_type)
                    if 0 <= tile_type < 5:
                        grid_obs[y, x, tile_type] = 1.0
        
        # Flatten grid
        grid_flat = grid_obs.flatten()
        
        # Player state
        player_obs = np.array([
            self.player.x / self.width,
            self.player.y / self.height,
            self.player.health / 100,
            self.player.score / 1000,
            self.current_step / self.max_steps
        ], dtype=np.float32)
        
        return np.concatenate([grid_flat, player_obs])
    
    def _get_info(self) -> dict:
        """Get info dictionary."""
        return {
            'crystals_collected': self.player.stats.crystals_collected,
            'crystals_remaining': self.grid.crystals_remaining,
            'health': self.player.health,
            'score': self.player.score,
            'step': self.current_step,
            'stealth_mode': self.stealth_mode,
            'fog_violations': self.fog_violations,
            'optimal_ratio': self.optimal_moves / max(self.total_moves, 1)
        }
    
    def _track_movement(self, old_pos: Tuple[int, int], new_pos: Tuple[int, int]) -> None:
        """Track movement for detection analysis."""
        self.movement_history.append({
            'from': old_pos,
            'to': new_pos,
            'stealth': self.stealth_mode,
            'step': self.current_step
        })
        
        # Check if this was a "fog violation" (moving toward hidden crystal)
        # In normal play, player can only see 3x3
        crystal_positions = [
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if self.grid.get_tile(x, y).tile_type == TileType.CRYSTAL
        ]
        
        if crystal_positions:
            # Find nearest crystal
            nearest = min(
                crystal_positions,
                key=lambda p: abs(p[0] - old_pos[0]) + abs(p[1] - old_pos[1])
            )
            
            old_dist = abs(nearest[0] - old_pos[0]) + abs(nearest[1] - old_pos[1])
            new_dist = abs(nearest[0] - new_pos[0]) + abs(nearest[1] - new_pos[1])
            
            # If crystal was outside 3x3 visibility but we moved toward it
            if old_dist > 2 and new_dist < old_dist:
                if not self.stealth_mode:
                    self.fog_violations += 1
                self.optimal_moves += 1
    
    def _calculate_detectability(self) -> float:
        """
        Calculate how detectable the current behavior is.
        
        This simulates what the anti-cheat would detect.
        """
        if self.detector_callback:
            # Use external detector
            return self.detector_callback(self.movement_history)
        
        # Simple heuristic detection
        score = 0.0
        
        # Fog violations are very suspicious
        score += min(0.5, self.fog_violations * 0.1)
        
        # Too-optimal pathing
        optimal_ratio = self.optimal_moves / max(self.total_moves, 1)
        if optimal_ratio > 0.8:
            score += 0.3
        elif optimal_ratio > 0.6:
            score += 0.1
        
        # If in stealth mode, reduce detectability
        if self.stealth_mode:
            score *= 0.5
        
        return min(1.0, score)
    
    def get_optimal_action(self) -> int:
        """Get the optimal action (for analysis/cheating)."""
        # Find nearest crystal
        crystal_positions = [
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if self.grid.get_tile(x, y).tile_type == TileType.CRYSTAL
        ]
        
        if not crystal_positions:
            # Head to exit
            exit_pos = self.grid._find_exit()
            if exit_pos:
                return self._get_direction_to(exit_pos)
            return 0  # NONE
        
        # Find nearest
        nearest = min(
            crystal_positions,
            key=lambda p: abs(p[0] - self.player.x) + abs(p[1] - self.player.y)
        )
        
        return self._get_direction_to(nearest)
    
    def _get_direction_to(self, target: Tuple[int, int]) -> int:
        """Get direction to move toward target."""
        dx = target[0] - self.player.x
        dy = target[1] - self.player.y
        
        if abs(dx) > abs(dy):
            if dx > 0:
                return 4  # RIGHT
            else:
                return 3  # LEFT
        else:
            if dy > 0:
                return 2  # DOWN
            elif dy < 0:
                return 1  # UP
        
        return 0  # NONE
    
    def render(self) -> Optional[np.ndarray]:
        """Render the environment."""
        # Simple text render for debugging
        grid_str = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                if x == self.player.x and y == self.player.y:
                    row.append('@')
                else:
                    tile = self.grid.get_tile(x, y)
                    if tile.tile_type == TileType.EMPTY:
                        row.append('.')
                    elif tile.tile_type == TileType.LAVA:
                        row.append('~')
                    elif tile.tile_type == TileType.CRYSTAL:
                        row.append('*')
                    elif tile.tile_type == TileType.WALL:
                        row.append('#')
                    elif tile.tile_type == TileType.EXIT:
                        row.append('E')
            grid_str.append(''.join(row))
        
        print('\n'.join(grid_str))
        print(f"Score: {self.player.score} | Crystals: {self.player.stats.crystals_collected}")
        print(f"Detectability: {self._calculate_detectability():.2%}")
        
        return None
