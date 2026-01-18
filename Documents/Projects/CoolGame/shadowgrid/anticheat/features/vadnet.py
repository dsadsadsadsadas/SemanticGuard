"""
ShadowGrid VADNet - Visual Aiming Detection Network

Analyzes the relationship between aiming behavior and performance
to distinguish human skill from automated aimbots.

Adapted for gridworld: "aiming" = directional decision making
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Deque, Optional
from collections import deque
import numpy as np


@dataclass
class AimEvent:
    """An aiming/decision event."""
    timestamp: float
    direction: int
    was_effective: bool        # Did this lead to crystal/success
    decision_time_ms: float    # Time to make this decision
    consecutive_count: int     # Consecutive same-direction moves


@dataclass
class VADNetConfig:
    """Configuration for VADNet analysis."""
    window_size: int = 100
    human_reaction_min_ms: float = 100.0   # Minimum human reaction time
    human_reaction_max_ms: float = 500.0   # Typical human max
    aimbot_consistency_threshold: float = 0.85  # Too consistent = bot


class VADNetAnalyzer:
    """
    VADNet (Visual Aiming Detection Network) for gridworld.
    
    Analyzes:
    - Decision timing patterns
    - Effectiveness rate (hit ratio analog)
    - Consistency vs human variance
    - Reaction time distribution
    
    Key insight: Humans have natural variance in timing and accuracy.
    Bots are often too consistent or have impossible timing.
    """
    
    def __init__(self, config: VADNetConfig = VADNetConfig()):
        self.config = config
        self.events: Deque[AimEvent] = deque(maxlen=config.window_size)
        
        # Tracking
        self.last_direction: Optional[int] = None
        self.last_decision_time: float = 0.0
        self.consecutive_count: int = 0
        
        # Cumulative stats
        self.total_decisions: int = 0
        self.effective_decisions: int = 0
        self.crystal_sequences: List[List[int]] = []  # Directions leading to crystal
        self.current_sequence: List[int] = []
    
    def record_decision(
        self,
        timestamp: float,
        direction: int,
        was_effective: bool = False
    ) -> None:
        """
        Record a directional decision.
        
        Args:
            timestamp: Time of decision
            direction: Direction chosen (1-4)
            was_effective: Whether this contributed to success
        """
        # Calculate decision time
        decision_time_ms = 0.0
        if self.last_decision_time > 0:
            decision_time_ms = (timestamp - self.last_decision_time) * 1000
        
        # Track consecutive moves
        if direction == self.last_direction:
            self.consecutive_count += 1
        else:
            self.consecutive_count = 1
        
        # Create event
        event = AimEvent(
            timestamp=timestamp,
            direction=direction,
            was_effective=was_effective,
            decision_time_ms=decision_time_ms,
            consecutive_count=self.consecutive_count
        )
        
        self.events.append(event)
        self.total_decisions += 1
        
        if was_effective:
            self.effective_decisions += 1
        
        # Track sequence
        self.current_sequence.append(direction)
        
        # Update state
        self.last_direction = direction
        self.last_decision_time = timestamp
    
    def record_crystal_collected(self) -> None:
        """Record that player collected a crystal (successful sequence)."""
        if self.current_sequence:
            self.crystal_sequences.append(self.current_sequence.copy())
        self.current_sequence = []
    
    def analyze(self) -> dict:
        """
        Perform VADNet analysis.
        
        Returns:
            Dictionary with analysis results
        """
        if len(self.events) < 10:
            return {
                'insufficient_data': True,
                'events_recorded': len(self.events)
            }
        
        events = list(self.events)
        
        # Timing analysis
        timing = self._analyze_timing(events)
        
        # Consistency analysis
        consistency = self._analyze_consistency(events)
        
        # Effectiveness analysis
        effectiveness = self._analyze_effectiveness(events)
        
        # Pattern analysis
        patterns = self._analyze_patterns(events)
        
        # Overall suspicion calculation
        suspicion_score = self._calculate_suspicion(
            timing, consistency, effectiveness, patterns
        )
        
        return {
            'timing': timing,
            'consistency': consistency,
            'effectiveness': effectiveness,
            'patterns': patterns,
            'suspicion_score': suspicion_score,
            'is_suspicious': suspicion_score > 0.6
        }
    
    def _analyze_timing(self, events: List[AimEvent]) -> dict:
        """Analyze decision timing."""
        decision_times = [e.decision_time_ms for e in events if e.decision_time_ms > 0]
        
        if not decision_times:
            return {'error': 'no timing data'}
        
        avg_time = np.mean(decision_times)
        std_time = np.std(decision_times)
        min_time = min(decision_times)
        max_time = max(decision_times)
        
        # Check for inhuman timing
        inhuman_fast = sum(1 for t in decision_times if t < self.config.human_reaction_min_ms)
        inhuman_ratio = inhuman_fast / len(decision_times)
        
        # Check for too-regular timing (bot signature)
        cv = std_time / avg_time if avg_time > 0 else 0  # Coefficient of variation
        too_regular = cv < 0.1  # Very low variance
        
        return {
            'avg_ms': avg_time,
            'std_ms': std_time,
            'min_ms': min_time,
            'max_ms': max_time,
            'inhuman_ratio': inhuman_ratio,
            'too_regular': too_regular,
            'coefficient_of_variation': cv
        }
    
    def _analyze_consistency(self, events: List[AimEvent]) -> dict:
        """Analyze decision consistency."""
        # Direction distribution
        directions = [e.direction for e in events]
        direction_counts = {}
        for d in directions:
            direction_counts[d] = direction_counts.get(d, 0) + 1
        
        # Entropy of direction choices
        probs = np.array(list(direction_counts.values())) / len(directions)
        entropy = -np.sum(probs * np.log2(probs + 1e-10))
        max_entropy = np.log2(len(direction_counts))
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
        
        # Consecutive same-direction analysis
        consecutive_lengths = [e.consecutive_count for e in events]
        avg_consecutive = np.mean(consecutive_lengths)
        max_consecutive = max(consecutive_lengths)
        
        # Check for too-consistent behavior
        too_consistent = normalized_entropy < 0.3 or avg_consecutive > 5
        
        return {
            'direction_distribution': direction_counts,
            'entropy': normalized_entropy,
            'avg_consecutive': avg_consecutive,
            'max_consecutive': max_consecutive,
            'too_consistent': too_consistent
        }
    
    def _analyze_effectiveness(self, events: List[AimEvent]) -> dict:
        """Analyze decision effectiveness."""
        effective_count = sum(1 for e in events if e.was_effective)
        total = len(events)
        
        effectiveness_rate = effective_count / total if total > 0 else 0
        
        # Check for superhuman effectiveness
        superhuman = effectiveness_rate > 0.85  # 85%+ success rate is suspicious
        
        # Trend analysis (is player getting "better" too fast?
        if total > 20:
            first_half = events[:total//2]
            second_half = events[total//2:]
            
            first_rate = sum(1 for e in first_half if e.was_effective) / len(first_half)
            second_rate = sum(1 for e in second_half if e.was_effective) / len(second_half)
            
            improvement = second_rate - first_rate
        else:
            improvement = 0.0
        
        return {
            'effectiveness_rate': effectiveness_rate,
            'effective_count': effective_count,
            'total_decisions': total,
            'superhuman': superhuman,
            'improvement_rate': improvement,
            'rapid_improvement': improvement > 0.3  # 30%+ improvement is unusual
        }
    
    def _analyze_patterns(self, events: List[AimEvent]) -> dict:
        """Analyze decision patterns."""
        if not self.crystal_sequences:
            return {'no_patterns': True}
        
        # Find common patterns in successful sequences
        pattern_freq = {}
        for seq in self.crystal_sequences:
            if len(seq) >= 2:
                # Look at pairs
                for i in range(len(seq) - 1):
                    pair = (seq[i], seq[i+1])
                    pattern_freq[pair] = pattern_freq.get(pair, 0) + 1
        
        if not pattern_freq:
            return {'no_patterns': True}
        
        # Most common transitions
        sorted_patterns = sorted(pattern_freq.items(), key=lambda x: x[1], reverse=True)
        top_pattern = sorted_patterns[0] if sorted_patterns else None
        
        # Check for too-predictable behavior
        max_freq = sorted_patterns[0][1] if sorted_patterns else 0
        total_transitions = sum(pattern_freq.values())
        predictability = max_freq / total_transitions if total_transitions > 0 else 0
        
        return {
            'top_pattern': top_pattern,
            'pattern_count': len(pattern_freq),
            'predictability': predictability,
            'too_predictable': predictability > 0.5
        }
    
    def _calculate_suspicion(
        self,
        timing: dict,
        consistency: dict,
        effectiveness: dict,
        patterns: dict
    ) -> float:
        """Calculate overall suspicion score (0-1)."""
        score = 0.0
        weights_total = 0.0
        
        # Timing factors
        if 'inhuman_ratio' in timing:
            score += timing['inhuman_ratio'] * 3.0  # Heavy weight
            weights_total += 3.0
        
        if timing.get('too_regular', False):
            score += 2.0
            weights_total += 2.0
        
        # Consistency factors
        if consistency.get('too_consistent', False):
            score += 1.5
            weights_total += 1.5
        
        # Effectiveness factors
        if effectiveness.get('superhuman', False):
            score += 2.5
            weights_total += 2.5
        
        if effectiveness.get('rapid_improvement', False):
            score += 1.0
            weights_total += 1.0
        
        # Pattern factors
        if patterns.get('too_predictable', False):
            score += 1.0
            weights_total += 1.0
        
        # Normalize
        if weights_total > 0:
            return min(1.0, score / weights_total)
        
        return 0.0
    
    def get_feature_vector(self) -> np.ndarray:
        """
        Get features as numpy array for ML model input.
        
        Returns:
            Array of 15 VADNet-specific features
        """
        analysis = self.analyze()
        
        features = np.zeros(15, dtype=np.float32)
        
        if analysis.get('insufficient_data', False):
            return features
        
        timing = analysis.get('timing', {})
        consistency = analysis.get('consistency', {})
        effectiveness = analysis.get('effectiveness', {})
        
        features[0] = timing.get('avg_ms', 0) / 1000
        features[1] = timing.get('std_ms', 0) / 1000
        features[2] = timing.get('min_ms', 0) / 1000
        features[3] = timing.get('inhuman_ratio', 0)
        features[4] = timing.get('coefficient_of_variation', 0)
        
        features[5] = consistency.get('entropy', 0)
        features[6] = consistency.get('avg_consecutive', 0) / 10
        features[7] = 1.0 if consistency.get('too_consistent', False) else 0.0
        
        features[8] = effectiveness.get('effectiveness_rate', 0)
        features[9] = effectiveness.get('improvement_rate', 0)
        features[10] = 1.0 if effectiveness.get('superhuman', False) else 0.0
        
        patterns = analysis.get('patterns', {})
        features[11] = patterns.get('predictability', 0)
        features[12] = 1.0 if patterns.get('too_predictable', False) else 0.0
        
        features[13] = analysis.get('suspicion_score', 0)
        features[14] = 1.0 if analysis.get('is_suspicious', False) else 0.0
        
        return features
