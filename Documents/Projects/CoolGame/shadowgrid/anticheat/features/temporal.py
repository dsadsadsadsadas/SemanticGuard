"""
ShadowGrid Temporal Feature Extraction

Extracts 44+ temporal features from player behavior for cheat detection.
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Deque, Optional
from collections import deque
import numpy as np

from ...game.player import MovementRecord, PlayerStats
from ...game.constants import Direction


# =============================================================================
# FEATURE DEFINITIONS
# =============================================================================

FEATURE_NAMES = [
    # Movement features (0-9)
    'velocity_x_avg', 'velocity_y_avg', 'velocity_magnitude_avg',
    'acceleration_x_avg', 'acceleration_y_avg', 'acceleration_magnitude_avg',
    'direction_change_rate', 'path_straightness',
    'wall_collision_rate', 'lava_proximity_avg',
    
    # Timing features (10-19)
    'input_frequency', 'input_regularity_std',
    'reaction_time_avg', 'reaction_time_std',
    'time_between_kills', 'time_to_first_crystal',
    'idle_time_ratio', 'sprint_time_ratio',
    'decision_latency_avg', 'action_prediction_accuracy',
    
    # Aiming features (20-29) - adapted for gridworld
    'yaw_delta_avg', 'yaw_delta_std', 'yaw_delta_max',
    'pitch_delta_avg', 'pitch_delta_std', 'pitch_delta_max',
    'aim_snap_count', 'aim_smoothness',
    'target_lock_duration', 'pre_aim_accuracy',
    
    # Combat/collection features (30-39)
    'kill_count', 'death_count', 'kd_ratio',
    'hit_rate', 'crystal_rate', 'damage_per_second',
    'crystal_collect_rate', 'optimal_path_deviation',
    'risk_taking_score', 'survival_efficiency',
    
    # Anomaly features (40-49)
    'impossible_move_count', 'speed_violation_count',
    'teleport_detection', 'state_desync_count',
    'input_timing_anomaly', 'prediction_accuracy',
    'fog_violation_score', 'knowledge_anomaly_score',
    'behavioral_consistency', 'session_variance'
]

NUM_FEATURES = len(FEATURE_NAMES)


@dataclass
class TemporalWindow:
    """Sliding window for temporal feature calculation."""
    size: int = 100
    
    # Movement
    velocities: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=100))
    accelerations: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=100))
    positions: Deque[Tuple[int, int]] = field(default_factory=lambda: deque(maxlen=100))
    directions: Deque[Direction] = field(default_factory=lambda: deque(maxlen=100))
    
    # Timing
    input_times: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    input_intervals: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    
    # Events
    crystal_times: Deque[float] = field(default_factory=lambda: deque(maxlen=50))
    death_times: Deque[float] = field(default_factory=lambda: deque(maxlen=50))
    lava_touches: Deque[float] = field(default_factory=lambda: deque(maxlen=50))
    
    # Validation
    invalid_moves: int = 0
    speed_violations: int = 0
    teleports: int = 0
    fog_violations: int = 0


class TemporalFeatures:
    """
    Extracts temporal features from player behavior.
    
    Used for:
    - Real-time Tier 1 detection (client-side)
    - Historical Tier 2 analysis (server-side)
    """
    
    # Thresholds
    MIN_INPUT_INTERVAL_MS = 150     # Inputs faster than 150ms are suspicious (normal human ~250-400ms)
    MAX_VELOCITY = 5.0              # Tiles per second (normal max ~3)
    SNAP_THRESHOLD = 3.0            # Direction change too fast
    
    def __init__(self, window_size: int = 100):
        self.window = TemporalWindow(size=window_size)
        self.session_start = time.time()
        self.first_crystal_time: Optional[float] = None
        self.last_direction: Optional[Direction] = None
        self.last_velocity: Tuple[float, float] = (0.0, 0.0)
    
    def record_movement(self, record: MovementRecord) -> None:
        """Record a movement for feature extraction."""
        # Position
        self.window.positions.append(record.to_pos)
        
        # Velocity
        velocity = record.velocity
        self.window.velocities.append(velocity)
        
        # Acceleration (change in velocity)
        if self.last_velocity != (0.0, 0.0):
            accel = (
                velocity[0] - self.last_velocity[0],
                velocity[1] - self.last_velocity[1]
            )
            self.window.accelerations.append(accel)
        
        self.last_velocity = velocity
        
        # Direction changes
        self.window.directions.append(record.direction)
        
        if self.last_direction and self.last_direction != record.direction:
            # Direction changed - check if it's a "snap"
            pass
        
        self.last_direction = record.direction
        
        # Input timing
        self.window.input_times.append(record.timestamp)
        
        if len(self.window.input_times) > 1:
            interval = record.timestamp - self.window.input_times[-2]
            self.window.input_intervals.append(interval * 1000)  # ms
            
            # Check for timing anomalies
            if interval * 1000 < self.MIN_INPUT_INTERVAL_MS:
                self.window.speed_violations += 1
        
        # Validation
        if not record.was_valid:
            self.window.invalid_moves += 1
        
        # Teleport detection
        if len(self.window.positions) > 1:
            prev = self.window.positions[-2]
            curr = record.to_pos
            distance = abs(curr[0] - prev[0]) + abs(curr[1] - prev[1])
            if distance > 1:  # Moved more than 1 tile in one step
                self.window.teleports += 1
    
    def record_crystal(self) -> None:
        """Record crystal collection."""
        now = time.time()
        self.window.crystal_times.append(now)
        if self.first_crystal_time is None:
            self.first_crystal_time = now
    
    def record_death(self) -> None:
        """Record player death."""
        self.window.death_times.append(time.time())
    
    def record_lava_touch(self) -> None:
        """Record lava touch."""
        self.window.lava_touches.append(time.time())
    
    def record_fog_violation(self) -> None:
        """Record when player seems to know what's in fog."""
        self.window.fog_violations += 1
    
    def extract_features(self) -> np.ndarray:
        """
        Extract all 50 features as a numpy array.
        
        Returns:
            np.ndarray of shape (50,)
        """
        features = np.zeros(NUM_FEATURES, dtype=np.float32)
        
        # --- Movement features (0-9) ---
        if self.window.velocities:
            vels = list(self.window.velocities)
            vx = [v[0] for v in vels]
            vy = [v[1] for v in vels]
            vmag = [math.sqrt(v[0]**2 + v[1]**2) for v in vels]
            
            features[0] = np.mean(vx)
            features[1] = np.mean(vy)
            features[2] = np.mean(vmag)
        
        if self.window.accelerations:
            accels = list(self.window.accelerations)
            ax = [a[0] for a in accels]
            ay = [a[1] for a in accels]
            amag = [math.sqrt(a[0]**2 + a[1]**2) for a in accels]
            
            features[3] = np.mean(ax)
            features[4] = np.mean(ay)
            features[5] = np.mean(amag)
        
        # Direction change rate
        if len(self.window.directions) > 1:
            changes = sum(
                1 for i in range(1, len(self.window.directions))
                if self.window.directions[i] != self.window.directions[i-1]
            )
            features[6] = changes / len(self.window.directions)
        
        # Path straightness
        if len(self.window.positions) > 2:
            start = self.window.positions[0]
            end = self.window.positions[-1]
            direct_dist = math.sqrt(
                (end[0] - start[0])**2 + (end[1] - start[1])**2
            )
            actual_dist = len(self.window.positions) - 1
            if actual_dist > 0:
                features[7] = direct_dist / actual_dist
        
        # Wall collision rate
        total_moves = self.window.invalid_moves + len(self.window.positions)
        if total_moves > 0:
            features[8] = self.window.invalid_moves / total_moves
        
        # Lava proximity (based on touches)
        session_time = time.time() - self.session_start
        if session_time > 0:
            features[9] = len(self.window.lava_touches) / session_time
        
        # --- Timing features (10-19) ---
        if self.window.input_intervals:
            intervals = list(self.window.input_intervals)
            features[10] = 1000.0 / np.mean(intervals) if np.mean(intervals) > 0 else 0  # inputs/sec
            features[11] = np.std(intervals)
            features[12] = np.mean(intervals)  # reaction time avg
            features[13] = np.std(intervals)   # reaction time std
        
        # Time between kills (deaths in this context)
        if len(self.window.death_times) > 1:
            death_intervals = [
                self.window.death_times[i] - self.window.death_times[i-1]
                for i in range(1, len(self.window.death_times))
            ]
            features[14] = np.mean(death_intervals)
        
        # Time to first crystal
        if self.first_crystal_time:
            features[15] = self.first_crystal_time - self.session_start
        
        # Idle time ratio
        if self.window.input_intervals:
            intervals = list(self.window.input_intervals)
            idle_threshold = 500  # ms
            idle_count = sum(1 for i in intervals if i > idle_threshold)
            features[16] = idle_count / len(intervals)
            
            # Sprint ratio (very fast inputs)
            sprint_count = sum(1 for i in intervals if i < 100)
            features[17] = sprint_count / len(intervals)
        
        features[18] = np.mean(list(self.window.input_intervals)) if self.window.input_intervals else 0
        features[19] = 0.0  # Prediction accuracy (requires more context)
        
        # --- Aiming features (20-29) ---
        # In gridworld, we interpret "aiming" as directional decisions
        if len(self.window.directions) > 1:
            # Direction changes simulate "yaw delta"
            dir_changes = []
            for i in range(1, len(self.window.directions)):
                if self.window.directions[i] != self.window.directions[i-1]:
                    dir_changes.append(1.0)
                else:
                    dir_changes.append(0.0)
            
            features[20] = np.mean(dir_changes) if dir_changes else 0
            features[21] = np.std(dir_changes) if dir_changes else 0
            features[22] = max(dir_changes) if dir_changes else 0
            
            # Copy for pitch (not really applicable in 2D)
            features[23] = features[20]
            features[24] = features[21]
            features[25] = features[22]
        
        # Snap count (sudden direction changes)
        features[26] = self._count_snaps()
        features[27] = 1.0 - features[26] / max(len(self.window.directions), 1)  # Smoothness
        features[28] = 0.0  # Target lock duration
        features[29] = 0.0  # Pre-aim accuracy
        
        # --- Combat/collection features (30-39) ---
        features[30] = len(self.window.crystal_times)  # "kills" = crystals
        features[31] = len(self.window.death_times)
        features[32] = features[30] / max(features[31], 1)  # K/D ratio
        features[33] = 0.0  # Hit rate (N/A)
        
        # Crystal rate
        if session_time > 0:
            features[34] = len(self.window.crystal_times) / session_time
        
        features[35] = 0.0  # Damage per second (N/A)
        features[36] = features[34]  # Crystal collect rate
        features[37] = 0.0  # Optimal path deviation (requires pathfinding)
        
        # Risk taking (lava touches per crystal)
        if len(self.window.crystal_times) > 0:
            features[38] = len(self.window.lava_touches) / len(self.window.crystal_times)
        
        # Survival efficiency
        if len(self.window.death_times) > 0:
            survival_time = session_time / len(self.window.death_times)
            features[39] = survival_time / 60.0  # Normalize to minutes
        else:
            features[39] = 1.0  # No deaths = max efficiency
        
        # --- Anomaly features (40-49) ---
        features[40] = self.window.invalid_moves
        features[41] = self.window.speed_violations
        features[42] = self.window.teleports
        features[43] = 0  # State desync (set by server)
        features[44] = self.window.speed_violations  # Input timing anomaly
        features[45] = 0.0  # Prediction accuracy
        features[46] = self.window.fog_violations
        features[47] = self.window.fog_violations / max(len(self.window.positions), 1)
        
        # Behavioral consistency (low variance = suspicious bot)
        if self.window.input_intervals:
            cv = np.std(list(self.window.input_intervals)) / max(np.mean(list(self.window.input_intervals)), 1)
            features[48] = cv
        
        # Session variance
        if len(self.window.velocities) > 1:
            vx_values = [v[0] for v in self.window.velocities]
            features[49] = np.var(vx_values)
        else:
            features[49] = 0
        
        return features
    
    def _count_snaps(self) -> int:
        """Count sudden direction changes (potential aimbot signature)."""
        snaps = 0
        directions = list(self.window.directions)
        
        for i in range(2, len(directions)):
            # Pattern: A -> B -> A (quick back-and-forth)
            if directions[i] == directions[i-2] and directions[i] != directions[i-1]:
                snaps += 1
        
        return snaps
    
    def get_feature_dict(self) -> Dict[str, float]:
        """Get features as a named dictionary."""
        features = self.extract_features()
        return {name: float(features[i]) for i, name in enumerate(FEATURE_NAMES)}


class FeatureExtractor:
    """
    High-level feature extractor that combines all feature types.
    
    Usage:
        extractor = FeatureExtractor()
        extractor.on_movement(record)
        extractor.on_crystal()
        features = extractor.get_features()
    """
    
    def __init__(self, player_id: str, window_size: int = 100):
        self.player_id = player_id
        self.temporal = TemporalFeatures(window_size)
        self.start_time = time.time()
    
    def on_movement(self, record: MovementRecord) -> None:
        """Process a movement record."""
        self.temporal.record_movement(record)
    
    def on_crystal(self) -> None:
        """Process crystal collection."""
        self.temporal.record_crystal()
    
    def on_death(self) -> None:
        """Process player death."""
        self.temporal.record_death()
    
    def on_lava(self) -> None:
        """Process lava touch."""
        self.temporal.record_lava_touch()
    
    def on_fog_violation(self) -> None:
        """Process fog of war violation."""
        self.temporal.record_fog_violation()
    
    def get_features(self) -> np.ndarray:
        """Get all features as numpy array."""
        return self.temporal.extract_features()
    
    def get_feature_dict(self) -> Dict[str, float]:
        """Get all features as dictionary."""
        return self.temporal.get_feature_dict()
    
    def get_suspicion_indicators(self) -> Dict[str, any]:
        """Get quick suspicion indicators."""
        return {
            'speed_violations': self.temporal.window.speed_violations,
            'teleports': self.temporal.window.teleports,
            'fog_violations': self.temporal.window.fog_violations,
            'invalid_moves': self.temporal.window.invalid_moves,
            'session_duration': time.time() - self.start_time
        }
