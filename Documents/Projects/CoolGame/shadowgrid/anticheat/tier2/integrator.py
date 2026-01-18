"""
ShadowGrid Tier 2 Integrator

Orchestrates all Tier 2 detection components.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum
import numpy as np

from .tabnet import TabNetDetector, PlayerHistory, HistoryStore
from .visual import VisualAnalyzer, VisualEvidence, MockVisualAnalyzer


class Verdict(Enum):
    """Final verdict for a player."""
    CLEAR = "clear"
    MONITOR = "monitor"
    REVIEW = "review"
    BAN = "ban"


@dataclass
class Tier2Result:
    """Complete Tier 2 analysis result."""
    player_id: str
    
    # Scoring
    tabnet_score: float
    visual_score: float
    combined_score: float
    
    # Verdict
    verdict: Verdict
    confidence: float
    
    # Evidence
    top_features: List[Tuple[str, float]]
    visual_findings: List[str]
    reasoning: str
    
    # Metadata
    analysis_time_ms: float
    tier1_score: float


class Tier2Integrator:
    """
    Integrates TabNet and Visual analysis for Tier 2 detection.
    
    Workflow:
    1. Receive flagged player from Tier 1
    2. Run TabNet analysis with session + historical features
    3. If TabNet flags, run visual analysis on replay
    4. Combine scores and evidence
    5. Return verdict and evidence for Tier 3
    """
    
    # Thresholds
    TABNET_VISUAL_THRESHOLD = 0.5  # TabNet score to trigger visual
    COMBINED_BAN_THRESHOLD = 0.85
    COMBINED_REVIEW_THRESHOLD = 0.6
    COMBINED_MONITOR_THRESHOLD = 0.3
    
    # Score weights
    TABNET_WEIGHT = 0.6
    VISUAL_WEIGHT = 0.4
    
    def __init__(
        self,
        tabnet_path: Optional[str] = None,
        use_visual: bool = True,
        groq_api_key: Optional[str] = None
    ):
        # TabNet detector
        self.tabnet = TabNetDetector()
        if tabnet_path:
            self.tabnet.load(tabnet_path)
        
        # Visual analyzer
        self.use_visual = use_visual
        if use_visual:
            try:
                self.visual = VisualAnalyzer(api_key=groq_api_key)
            except:
                self.visual = MockVisualAnalyzer()
        else:
            self.visual = MockVisualAnalyzer()
        
        # History store
        self.history_store = HistoryStore()
    
    def analyze(
        self,
        player_id: str,
        session_features: np.ndarray,
        tier1_score: float,
        replay_frames: Optional[List[dict]] = None,
        replay_id: Optional[str] = None
    ) -> Tier2Result:
        """
        Perform complete Tier 2 analysis.
        
        Args:
            player_id: Player to analyze
            session_features: Features from Tier 1 (50 dims)
            tier1_score: Score from Tier 1 detector
            replay_frames: Optional replay data for visual analysis
            replay_id: Optional replay ID
            
        Returns:
            Tier2Result with verdict and evidence
        """
        start_time = time.time()
        
        # Get player history
        history = self.history_store.get(player_id)
        
        # TabNet analysis
        tabnet_score, tabnet_flag, attention = self.tabnet.predict(
            session_features, history
        )
        
        # Get top features
        feature_names = self._get_feature_names()
        top_features = self.tabnet.get_top_features(
            attention, feature_names, top_k=10
        )
        
        # Visual analysis (if TabNet is suspicious enough)
        visual_score = 0.0
        visual_findings = []
        visual_reasoning = ""
        
        if tabnet_score >= self.TABNET_VISUAL_THRESHOLD and replay_frames:
            visual_evidence = self.visual.analyze_replay_segment(
                replay_id or "unknown",
                player_id,
                replay_frames,
                cheat_type='general'
            )
            
            # Convert suspicion level to score
            visual_score = self._suspicion_to_score(visual_evidence.suspicion_level)
            visual_score *= visual_evidence.confidence
            
            visual_findings = visual_evidence.findings
            visual_reasoning = visual_evidence.reasoning
        
        # Combine scores
        if replay_frames and tabnet_score >= self.TABNET_VISUAL_THRESHOLD:
            combined_score = (
                self.TABNET_WEIGHT * tabnet_score +
                self.VISUAL_WEIGHT * visual_score
            )
        else:
            combined_score = tabnet_score
        
        # Determine verdict
        verdict = self._determine_verdict(combined_score, tabnet_score, visual_score)
        
        # Calculate confidence
        if visual_score > 0:
            confidence = min(tabnet_score, visual_score)  # Both must agree
        else:
            confidence = tabnet_score * 0.8  # Lower confidence without visual
        
        # Prepare reasoning
        reasoning = self._generate_reasoning(
            tabnet_score, visual_score, top_features, visual_findings
        )
        
        # Update history with this session
        self.history_store.update_from_session(player_id, {
            'flagged': combined_score > self.COMBINED_MONITOR_THRESHOLD
        })
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return Tier2Result(
            player_id=player_id,
            tabnet_score=tabnet_score,
            visual_score=visual_score,
            combined_score=combined_score,
            verdict=verdict,
            confidence=confidence,
            top_features=top_features,
            visual_findings=visual_findings,
            reasoning=reasoning,
            analysis_time_ms=elapsed_ms,
            tier1_score=tier1_score
        )
    
    def _suspicion_to_score(self, level: str) -> float:
        """Convert suspicion level to numeric score."""
        mapping = {
            'low': 0.2,
            'medium': 0.5,
            'high': 0.8,
            'certain': 1.0
        }
        return mapping.get(level, 0.5)
    
    def _determine_verdict(
        self,
        combined: float,
        tabnet: float,
        visual: float
    ) -> Verdict:
        """Determine final verdict based on scores."""
        # High combined = ban
        if combined >= self.COMBINED_BAN_THRESHOLD:
            return Verdict.BAN
        
        # Medium combined or high single = review
        if combined >= self.COMBINED_REVIEW_THRESHOLD:
            return Verdict.REVIEW
        
        # Low combined but some signal = monitor
        if combined >= self.COMBINED_MONITOR_THRESHOLD:
            return Verdict.MONITOR
        
        return Verdict.CLEAR
    
    def _generate_reasoning(
        self,
        tabnet_score: float,
        visual_score: float,
        top_features: List[Tuple[str, float]],
        visual_findings: List[str]
    ) -> str:
        """Generate human-readable reasoning."""
        parts = []
        
        parts.append(f"TabNet score: {tabnet_score:.2%}")
        
        if top_features:
            feature_str = ", ".join(
                f"{name}: {score:.2f}"
                for name, score in top_features[:3]
            )
            parts.append(f"Key features: {feature_str}")
        
        if visual_score > 0:
            parts.append(f"Visual score: {visual_score:.2%}")
        
        if visual_findings:
            parts.append(f"Visual findings: {'; '.join(visual_findings[:3])}")
        
        return " | ".join(parts)
    
    def _get_feature_names(self) -> List[str]:
        """Get combined feature names."""
        session_names = [
            'velocity_x_avg', 'velocity_y_avg', 'velocity_magnitude_avg',
            'acceleration_x_avg', 'acceleration_y_avg', 'acceleration_magnitude_avg',
            'direction_change_rate', 'path_straightness',
            'wall_collision_rate', 'lava_proximity_avg',
            'input_frequency', 'input_regularity_std',
            'reaction_time_avg', 'reaction_time_std',
            'time_between_kills', 'time_to_first_crystal',
            'idle_time_ratio', 'sprint_time_ratio',
            'decision_latency_avg', 'action_prediction_accuracy',
            'yaw_delta_avg', 'yaw_delta_std', 'yaw_delta_max',
            'pitch_delta_avg', 'pitch_delta_std', 'pitch_delta_max',
            'aim_snap_count', 'aim_smoothness',
            'target_lock_duration', 'pre_aim_accuracy',
            'kill_count', 'death_count', 'kd_ratio',
            'hit_rate', 'crystal_rate', 'damage_per_second',
            'crystal_collect_rate', 'optimal_path_deviation',
            'risk_taking_score', 'survival_efficiency',
            'impossible_move_count', 'speed_violation_count',
            'teleport_detection', 'state_desync_count',
            'input_timing_anomaly', 'prediction_accuracy',
            'fog_violation_score', 'knowledge_anomaly_score',
            'behavioral_consistency', 'session_variance'
        ]
        
        history_names = [
            'hist_total_sessions', 'hist_playtime_hours',
            'hist_avg_kd', 'hist_avg_crystal_rate',
            'hist_avg_ttk', 'hist_avg_hit_rate',
            'hist_avg_hit_rate_moving', 'hist_avg_precision',
            'hist_level', 'hist_level_up_speed',
            'hist_previous_flags', 'hist_previous_bans',
            'hist_tier1_flag_rate', 'hist_avg_input_freq',
            'hist_avg_reaction', 'hist_movement_entropy'
        ]
        
        return session_names + history_names
    
    def batch_analyze(
        self,
        cases: List[Dict]
    ) -> List[Tier2Result]:
        """
        Analyze multiple players efficiently.
        
        Args:
            cases: List of dicts with player_id, session_features, tier1_score, etc.
            
        Returns:
            List of Tier2Results
        """
        results = []
        
        for case in cases:
            result = self.analyze(
                player_id=case['player_id'],
                session_features=case['session_features'],
                tier1_score=case.get('tier1_score', 0.5),
                replay_frames=case.get('replay_frames'),
                replay_id=case.get('replay_id')
            )
            results.append(result)
        
        return results
    
    def get_cases_for_tier3(
        self,
        results: List[Tier2Result],
        verdict_filter: Optional[List[Verdict]] = None
    ) -> List[Tier2Result]:
        """
        Filter results that need Tier 3 (human) review.
        
        Args:
            results: List of Tier2 results
            verdict_filter: Verdicts to include (default: REVIEW)
            
        Returns:
            Filtered list
        """
        if verdict_filter is None:
            verdict_filter = [Verdict.REVIEW]
        
        return [
            r for r in results
            if r.verdict in verdict_filter
        ]
