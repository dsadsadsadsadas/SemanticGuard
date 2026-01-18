"""
ShadowGrid Movement Heatmap Generator

Creates 2D spatial heatmaps of player movement for pattern analysis.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import numpy as np


@dataclass
class HeatmapConfig:
    """Configuration for heatmap generation."""
    grid_width: int = 20
    grid_height: int = 20
    decay_rate: float = 0.99        # Per-tick decay
    time_weight: bool = True        # Weight by time spent
    normalize: bool = True          # Normalize to 0-1 range


class HeatmapGenerator:
    """
    Generates 2D heatmaps from player movement data.
    
    Use cases:
    - Detect non-human exploration patterns
    - Identify ESP/wallhack behavior (too-direct paths to hidden items)
    - Compare individual behavior to population baseline
    """
    
    def __init__(self, config: HeatmapConfig = HeatmapConfig()):
        self.config = config
        self.heatmap = np.zeros((config.grid_height, config.grid_width), dtype=np.float32)
        self.visit_count = np.zeros((config.grid_height, config.grid_width), dtype=np.int32)
        self.time_spent = np.zeros((config.grid_height, config.grid_width), dtype=np.float32)
        
        self.last_position: Optional[Tuple[int, int]] = None
        self.last_time: float = 0.0
        self.total_time: float = 0.0
    
    def record_position(self, x: int, y: int, timestamp: float) -> None:
        """Record player at a position."""
        if not (0 <= x < self.config.grid_width and 0 <= y < self.config.grid_height):
            return
        
        # Update visit count
        self.visit_count[y][x] += 1
        
        # Update time spent
        if self.last_position is not None and self.last_time > 0:
            time_delta = timestamp - self.last_time
            self.time_spent[y][x] += time_delta
            self.total_time += time_delta
        
        # Update heatmap intensity
        self.heatmap[y][x] += 1.0
        
        # Track position
        self.last_position = (x, y)
        self.last_time = timestamp
    
    def apply_decay(self) -> None:
        """Apply time-based decay to heatmap."""
        self.heatmap *= self.config.decay_rate
    
    def get_heatmap(self) -> np.ndarray:
        """
        Get the current heatmap.
        
        Returns:
            2D numpy array of heat values
        """
        result = self.heatmap.copy()
        
        if self.config.time_weight and self.total_time > 0:
            # Weight by normalized time spent
            time_weights = self.time_spent / self.total_time
            result = result * (1 + time_weights)
        
        if self.config.normalize and result.max() > 0:
            result = result / result.max()
        
        return result
    
    def get_visit_map(self) -> np.ndarray:
        """Get visit count map."""
        return self.visit_count.copy()
    
    def analyze_pattern(self) -> dict:
        """
        Analyze the movement pattern for anomalies.
        
        Returns:
            Dictionary with analysis metrics
        """
        heatmap = self.get_heatmap()
        
        # Coverage: what fraction of map was visited
        visited_tiles = np.sum(self.visit_count > 0)
        total_tiles = self.config.grid_width * self.config.grid_height
        coverage = visited_tiles / total_tiles
        
        # Concentration: how focused is the movement
        if heatmap.sum() > 0:
            concentration = np.max(heatmap) / np.mean(heatmap[heatmap > 0])
        else:
            concentration = 0.0
        
        # Entropy: randomness of movement
        flat = heatmap.flatten()
        flat = flat[flat > 0]  # Only non-zero values
        if len(flat) > 0:
            probs = flat / flat.sum()
            entropy = -np.sum(probs * np.log2(probs + 1e-10))
            max_entropy = np.log2(len(flat))
            normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
        else:
            normalized_entropy = 0.0
        
        # Edge preference (bots often avoid edges, or always use edges)
        edge_mask = np.zeros_like(self.visit_count, dtype=bool)
        edge_mask[0, :] = True
        edge_mask[-1, :] = True
        edge_mask[:, 0] = True
        edge_mask[:, -1] = True
        
        edge_visits = self.visit_count[edge_mask].sum()
        total_visits = self.visit_count.sum()
        edge_ratio = edge_visits / total_visits if total_visits > 0 else 0
        
        # Expected edge ratio for uniform distribution
        expected_edge_ratio = edge_mask.sum() / edge_mask.size
        edge_preference = edge_ratio / expected_edge_ratio if expected_edge_ratio > 0 else 0
        
        return {
            'coverage': coverage,
            'concentration': concentration,
            'entropy': normalized_entropy,
            'edge_preference': edge_preference,
            'total_visits': int(total_visits),
            'unique_tiles': int(visited_tiles),
            'suspicious': self._is_suspicious(coverage, concentration, normalized_entropy)
        }
    
    def _is_suspicious(
        self,
        coverage: float,
        concentration: float,
        entropy: float
    ) -> bool:
        """Check if pattern is suspicious."""
        # Too perfect coverage (exploration bot)
        if coverage > 0.95:
            return True
        
        # Too concentrated (knows exactly where to go)
        if concentration > 10.0:
            return True
        
        # Too uniform (automated exploration)
        if entropy > 0.95:
            return True
        
        # Too low entropy (memorized path)
        if entropy < 0.2 and coverage > 0.3:
            return True
        
        return False
    
    def compare_to_baseline(self, baseline: np.ndarray) -> float:
        """
        Compare current heatmap to a baseline.
        
        Args:
            baseline: Expected heatmap from normal players
            
        Returns:
            Similarity score (0-1, higher = more similar to baseline)
        """
        current = self.get_heatmap()
        
        if baseline.shape != current.shape:
            return 0.0
        
        # Normalize both
        if baseline.max() > 0:
            baseline = baseline / baseline.max()
        if current.max() > 0:
            current = current / current.max()
        
        # Compute cosine similarity
        dot = np.sum(baseline * current)
        norm_b = np.sqrt(np.sum(baseline ** 2))
        norm_c = np.sqrt(np.sum(current ** 2))
        
        if norm_b == 0 or norm_c == 0:
            return 0.0
        
        return dot / (norm_b * norm_c)
    
    def to_image(self, colormap: str = 'hot') -> np.ndarray:
        """
        Convert heatmap to RGB image array.
        
        Args:
            colormap: Matplotlib colormap name
            
        Returns:
            RGB array of shape (height, width, 3)
        """
        try:
            import matplotlib.pyplot as plt
            
            heatmap = self.get_heatmap()
            cmap = plt.get_cmap(colormap)
            colored = cmap(heatmap)[:, :, :3]  # Drop alpha
            
            return (colored * 255).astype(np.uint8)
        
        except ImportError:
            # Fallback: grayscale
            heatmap = self.get_heatmap()
            gray = (heatmap * 255).astype(np.uint8)
            return np.stack([gray, gray, gray], axis=-1)
    
    def reset(self) -> None:
        """Reset the heatmap."""
        self.heatmap.fill(0)
        self.visit_count.fill(0)
        self.time_spent.fill(0)
        self.last_position = None
        self.last_time = 0.0
        self.total_time = 0.0


class PopulationHeatmap:
    """
    Aggregates heatmaps across multiple players to create a baseline.
    """
    
    def __init__(self, width: int = 20, height: int = 20):
        self.width = width
        self.height = height
        self.aggregate = np.zeros((height, width), dtype=np.float64)
        self.player_count = 0
    
    def add_player_heatmap(self, heatmap: np.ndarray) -> None:
        """Add a player's heatmap to the aggregate."""
        if heatmap.shape != (self.height, self.width):
            return
        
        # Normalize before adding
        if heatmap.max() > 0:
            normalized = heatmap / heatmap.max()
        else:
            normalized = heatmap
        
        self.aggregate += normalized
        self.player_count += 1
    
    def get_baseline(self) -> np.ndarray:
        """Get the averaged baseline heatmap."""
        if self.player_count == 0:
            return np.zeros((self.height, self.width))
        
        return self.aggregate / self.player_count
    
    def identify_outliers(
        self,
        player_heatmap: np.ndarray,
        threshold: float = 0.5
    ) -> bool:
        """
        Check if a player's heatmap deviates significantly from baseline.
        
        Args:
            player_heatmap: The player's heatmap
            threshold: Similarity threshold (below = outlier)
            
        Returns:
            True if player is an outlier
        """
        baseline = self.get_baseline()
        
        # Create temporary generator for comparison
        gen = HeatmapGenerator(HeatmapConfig(
            grid_width=self.width,
            grid_height=self.height
        ))
        gen.heatmap = player_heatmap
        
        similarity = gen.compare_to_baseline(baseline)
        
        return similarity < threshold
