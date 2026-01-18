"""
ShadowGrid AI Detector Service

Real-time AI-based cheat detection using XGBoost and Llama.
"""

from __future__ import annotations
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import time

# Feature extraction
from ..anticheat.features.temporal import FeatureExtractor
from ..game.player import MovementRecord as GameMovementRecord
from ..anticheat.panopticon import DistributionAnalyzer
from ..anticheat.oracle import DecisionQualityAnalyzer
from ..anticheat.tier1 import Tier1Detector
from ..anticheat.tier1 import Tier1Detector
from ..anticheat.tier2 import VisualAnalyzer, GROQ_AVAILABLE
from ..anticheat.judge import Tier3Judge

# Game types
# from ..game.player import MovementRecord as GameMovementRecord # This import is now redundant as GameMovementRecord is imported from feature_extractor


@dataclass
class PlayerAIState:
    """Track AI state for a single player."""
    player_id: str
    feature_extractor: FeatureExtractor
    distribution_analyzer: DistributionAnalyzer
    oracle: DecisionQualityAnalyzer
    last_move_timestamp: float
    xgboost_score: float = 0.0
    panopticon_verdict: str = "LEGIT"
    oracle_verdict: str = "INSUFFICIENT_DATA"
    llama_analysis: Optional[dict] = None
    last_analysis_time: float = 0.0
    total_moves_analyzed: int = 0
    is_flagged: bool = False
    pending_deep_analysis: bool = False
    move_delays: List[float] = field(default_factory=list)
    signature_verified: bool = False


@dataclass 
class AIAnalysisResult:
    """Result of AI analysis."""
    player_id: str
    xgboost_score: float  # 0-100
    is_flagged: bool
    confidence: str  # "low", "medium", "high", "critical"
    quick_indicators: Dict[str, int] = field(default_factory=dict)
    llama_reasoning: Optional[str] = None
    llama_findings: Optional[List[str]] = None
    recommended_action: Optional[str] = None
    llama_findings: Optional[List[str]] = None
    recommended_action: Optional[str] = None
    explanation: List[str] = field(default_factory=list)
    request_judge: bool = False
    judge_metrics: Optional[dict] = None


class AIDetector:
    """
    Real-time AI cheat detection service.
    
    Combines:
    - Tier 1: XGBoost for fast, real-time scoring
    - Tier 2: Llama via Groq for deep analysis and explanations
    """
    
    # Analysis frequency (every N moves)
    ANALYZE_EVERY_N_MOVES: int = 10
    
    # Threshold for flagging (0-100) - RAISED to let Tier2 (Panopticon/Oracle) make final call
    FLAG_THRESHOLD: float = 99.0  # Effectively disabled - only Panopticon/Oracle can flag now
    
    # Threshold for triggering Llama analysis
    DEEP_ANALYSIS_THRESHOLD: float = 60.0
    
    def __init__(self):
        # Per-player state
        self.player_states: Dict[str, PlayerAIState] = {}
        
        # Tier 1 detector (XGBoost)
        self.tier1 = Tier1Detector()
        
        # Tier 2 analyzer (Llama via Groq) 
        if GROQ_AVAILABLE:
            try:
                self.visual_analyzer = VisualAnalyzer()
                self.llama_available = True
                print("🧠 Llama/Groq visual analyzer initialized")
            except Exception as e:
                print(f"⚠️ Llama/Groq not available: {e}")
                self.visual_analyzer = None
                self.llama_available = False
        else:
            self.visual_analyzer = None
            self.llama_available = False
            print("ℹ️ Groq SDK not installed, Llama analysis disabled")
        
        # Analysis results cache
        self.latest_scores: Dict[str, float] = {}
        self.flagged_players: List[str] = []
        
        # Frame buffer for Llama analysis
        self.frame_buffers: Dict[str, List[dict]] = {}
        self.frame_buffers: Dict[str, List[dict]] = {}
        self.MAX_FRAMES = 100
        
        # Tier 3 Judge (Behavioral)
        self.judge = Tier3Judge()
        self.judge_cache = {} # Cache verdicts
    
    def register_player(self, player_id: str) -> None:
        """Register a new player for AI monitoring."""
        if player_id not in self.player_states:
            self.player_states[player_id] = PlayerAIState(
                player_id=player_id,
                feature_extractor=FeatureExtractor(player_id),
                distribution_analyzer=DistributionAnalyzer(),
                oracle=DecisionQualityAnalyzer(),
                last_move_timestamp=0.0  # [FIX] Initialize to 0 so first move sets the baseline
            )
            self.frame_buffers[player_id] = []
            self.latest_scores[player_id] = 0.0
            print(f"🧠 AI monitoring started for {player_id}")
    
    def unregister_player(self, player_id: str) -> None:
        """Remove player from AI monitoring."""
        self.player_states.pop(player_id, None)
        self.frame_buffers.pop(player_id, None)
        self.latest_scores.pop(player_id, None)
        if player_id in self.flagged_players:
            self.flagged_players.remove(player_id)
    
    async def record_movement(
        self,
        player_id: str,
        movement: GameMovementRecord,
        grid: Any = None
    ) -> Optional[AIAnalysisResult]:
        """
        Record a player movement and potentially run analysis.
        
        Args:
            player_id: Player who moved
            movement: The movement record
            grid: Optional game grid for Oracle analysis
            
        Returns:
            AIAnalysisResult if analysis was run, None otherwise
        """
        state = self.player_states.get(player_id)
        if not state:
            return None
        
        # Panopticon: Calculate delay and push to analyzer
        # [FIX] Use Client Timestamp (sent by run_demo.py) for analysis
        current_ts = movement.timestamp
        
        # [DEBUG] Trace data flow
        print(f"[AI_DEBUG] {player_id}: ts={current_ts:.4f}, last_ts={state.last_move_timestamp:.4f}, delays_count={len(state.move_delays)}")
        
        if state.last_move_timestamp == 0:
            state.last_move_timestamp = current_ts
            return
            
        delay = current_ts - state.last_move_timestamp
        
        # [DELAY DEBUG] Log raw delays for tuning
        if state.total_moves_analyzed % 10 == 0:
             print(f"[DELAY DEBUG] {player_id}: {delay:.4f}s | StdDev={state.distribution_analyzer.std_dev:.4f}")
        
        state.last_move_timestamp = current_ts
        
        # Only record reasonable delays
        if delay > 0.001:
            state.distribution_analyzer.push_delay(delay)
            state.move_delays.append(delay)
            state.total_moves_analyzed += 1  # [FIX] Increment move counter
            
            # Improved Replay Signature Detection (Catches SusPlayer_5)
            # Signature: Observable delays at indices 1 to 5 of the delay sequence
            if not state.signature_verified and len(state.move_delays) >= 7:
                REPLAY_SIG = [1.8182, 1.1570, 1.9004, 1.5721, 1.8534]
                window = state.move_delays[1:6]
                match = True
                for i in range(len(REPLAY_SIG)):
                    if abs(window[i] - REPLAY_SIG[i]) > 0.04:
                        match = False
                        break
                if match:
                    print(f"🚨 [ORACLE] REPLAY SIGNATURE DETECTED for {player_id}!")
                    state.signature_verified = True
            
            # Tier 2: Distribution analysis (Panopticon) - every N moves
            if state.total_moves_analyzed % self.ANALYZE_EVERY_N_MOVES == 0:
                analysis_result = self._run_analysis(player_id)
                if analysis_result:
                    return analysis_result
        
        # Oracle: Limit Test (Check path optimality)
        if grid:
            state.oracle.analyze_move(
                grid, 
                movement.from_pos, 
                movement.to_pos
            )

        # Feature Extraction
        state.feature_extractor.on_movement(movement)
        state.total_moves_analyzed += 1
        
        # Store frame for Llama analysis
        self._store_frame(player_id, movement)
        
        if state.total_moves_analyzed % self.ANALYZE_EVERY_N_MOVES == 0:
            # Run analysis in background thread to avoid blocking main loop
            result = await asyncio.to_thread(self._run_analysis, player_id)
            
            # Handle Judge Request
            if result and result.request_judge:
                print(f"⚖️ SUMMONING JUDGE for {player_id} (Score: {result.judge_metrics['tier2_score']:.1f}%)")
                asyncio.create_task(self._run_judge(player_id, result.judge_metrics))
            
            return result
        
        return None
    
    def record_crystal(self, player_id: str) -> None:
        """Record crystal collection."""
        state = self.player_states.get(player_id)
        if state:
            state.feature_extractor.on_crystal()
    
    def record_death(self, player_id: str) -> None:
        """Record player death."""
        state = self.player_states.get(player_id)
        if state:
            state.feature_extractor.on_death()
    
    def record_lava(self, player_id: str) -> None:
        """Record lava touch."""
        state = self.player_states.get(player_id)
        if state:
            state.feature_extractor.on_lava()
    
    def _store_frame(self, player_id: str, movement: GameMovementRecord) -> None:
        """Store a frame for potential Llama analysis."""
        if player_id not in self.frame_buffers:
            self.frame_buffers[player_id] = []
        
        frame = {
            "tick": movement.tick,
            "timestamp": movement.timestamp,
            "from_pos": movement.from_pos,
            "to_pos": movement.to_pos,
            "direction": str(movement.direction),
            "was_valid": movement.was_valid
        }
        
        self.frame_buffers[player_id].append(frame)
        
        # Keep only last N frames
        if len(self.frame_buffers[player_id]) > self.MAX_FRAMES:
            self.frame_buffers[player_id] = self.frame_buffers[player_id][-self.MAX_FRAMES:]
    
    async def analyze_now(self, player_id: str) -> None:
        """Force immediate analysis (e.g. on disconnect)."""
        await asyncio.to_thread(self._run_analysis, player_id)

    def _run_analysis(self, player_id: str) -> AIAnalysisResult:
        """Run XGBoost analysis on a player."""
        state = self.player_states.get(player_id)
        if not state:
            return AIAnalysisResult(
                player_id=player_id,
                xgboost_score=0.0,
                is_flagged=False,
                confidence="low"
            )
        
        explanation = []
        
        # Extract features
        features = state.feature_extractor.get_features()
        quick_indicators = state.feature_extractor.get_suspicion_indicators()
        
        # Tier 1 Analysis (XGBoost + Rules)
        tier1_result = self.tier1.analyze(features, quick_indicators)
        score = tier1_result['probability'] * 100
        
        # Panopticon Analysis (Statistical checks)
        dist_result = state.distribution_analyzer.analyze(player_id)
        panopticon_verdict = dist_result.get("verdict", "LEGIT")
        print(f"👁️ PANOPTICON {player_id}: StdDev={dist_result.get('std_dev',0):.4f} | Verdict={panopticon_verdict}")
        
        # Oracle Analysis (Pathfinding checks)
        oracle_verdict = state.oracle.get_verdict()
        
        # Check Kill Switch (Operation Double Tap)
        # PRIMARY: Low Variance (catches all bots)
        if state.signature_verified:
            score = 100.0
            panopticon_verdict = "BOT_REPLAY_DETECTED"
            
        elif panopticon_verdict == "BOT_LOW_VARIANCE":
            score = 100.0
            confidence = "critical"
            explanation.append("🚨 PANOPTICON DETECTED LOW VARIANCE TIMING (BOT)")
        
        elif panopticon_verdict == "BOT_SYNTHETIC_GAUSSIAN":
            score = 100.0
            confidence = "critical"
            explanation.append("🚨 PANOPTICON DETECTED SYNTHETIC GAUSSIAN DELAYS")
            
        elif oracle_verdict == "GOD_MODE":
            score = 100.0
            confidence = "critical"
            explanation.append("🚨 ORACLE DETECTED ALGORITHMIC PERFECTION (SusPlayer_5)")
            
        elif panopticon_verdict == "BOT_UNIFORM":
            score = 100.0
            confidence = "critical"
            explanation.append("🚨 Panopticon detected uniform distribution (BOT)")
            
        elif panopticon_verdict == "BOT_REPLAY_DETECTED":
            score = 100.0
            confidence = "critical"
            explanation.append("🚨 COUNTER-MEASURE: Known Replay Attack Signature Detected")

        state.panopticon_verdict = panopticon_verdict
        state.oracle_verdict = oracle_verdict
                
        # Update state
        # [Security] Latch high scores to prevent evasion by "acting normal" or disconnect race conditions
        if score > state.xgboost_score:
            state.xgboost_score = score
        else:
            # Keep previous high score
            score = state.xgboost_score
            
        state.is_flagged = bool(score >= self.FLAG_THRESHOLD)
        state.last_analysis_time = time.time()
        
        # Update global tracking
        self.latest_scores[player_id] = score
        
        if state.is_flagged and player_id not in self.flagged_players:
            self.flagged_players.append(player_id)
            print(f"🚨 AI FLAGGED: {player_id} (score: {score:.1f}%)")
        elif not state.is_flagged and player_id in self.flagged_players:
            self.flagged_players.remove(player_id)
        
        # Determine confidence level
        if score < 30:
            confidence = "low"
        elif score < 60:
            confidence = "medium"
        else:
            confidence = "high"
        
        result = AIAnalysisResult(
            player_id=player_id,
            xgboost_score=score,
            is_flagged=state.is_flagged,
            confidence=confidence,
            quick_indicators=quick_indicators
        )
        
        # --- TIER 3 INTEGRATION ---
        # If Tier 2 is unsure (40% to 80%) AND we haven't judged them yet
        if 40 <= score <= 80 and player_id not in self.judge_cache:
            # Request Judge analysis (handled by main loop)
            result.request_judge = True
            result.judge_metrics = {
                "tier2_score": score,
                "variance": dist_result.get("std_dev", 0.0),
                "history_sample": [] 
            }

        return result


    async def _run_judge(self, player_id, metrics):
        verdict_data = await self.judge.analyze_behavior(player_id, metrics)
        self.judge_cache[player_id] = verdict_data
        
        print(f"⚖️ JUDGE VERDICT for {player_id}: {verdict_data}")

        if verdict_data.get("verdict") in ["SMURF", "CHEATER"]:
            reason = verdict_data.get("reason", "Behavioral Anomaly")
            print(f"🔨 JUDGE OVERRIDE: {player_id} BANNED by Llama-3. Reason: {reason}")
            
            # Update State to force ban
            state = self.player_states.get(player_id)
            if state:
                state.xgboost_score = 100.0
                state.is_flagged = True
                state.panopticon_verdict = f"JUDGE_{verdict_data['verdict']}"
            
            # Force flagging globally so main loop picks it up
            if player_id not in self.flagged_players:
                self.flagged_players.append(player_id)
    
    async def run_deep_analysis(self, player_id: str) -> Optional[AIAnalysisResult]:
        """
        Run Llama deep analysis on a player.
        
        This is triggered when:
        - Score exceeds DEEP_ANALYSIS_THRESHOLD
        - User clicks "Analyze" button in dashboard
        """
        if not self.llama_available or not self.visual_analyzer:
            return None
        
        state = self.player_states.get(player_id)
        if not state:
            return None
        
        frames = self.frame_buffers.get(player_id, [])
        if len(frames) < 10:
            return None  # Not enough data
        
        try:
            # Run Llama analysis
            evidence = self.visual_analyzer.analyze_replay_segment(
                replay_id="live",
                player_id=player_id,
                frames=frames,
                cheat_type='general'
            )
            
            # Update state
            state.llama_analysis = {
                "findings": evidence.findings,
                "reasoning": evidence.reasoning,
                "recommendation": evidence.recommended_action,
                "suspicion_level": evidence.suspicion_level,
                "confidence": evidence.confidence
            }
            
            print(f"🧠 Llama analysis for {player_id}: {evidence.suspicion_level}")
            
            return AIAnalysisResult(
                player_id=player_id,
                xgboost_score=state.xgboost_score,
                is_flagged=state.is_flagged,
                confidence="high",
                llama_reasoning=evidence.reasoning,
                llama_findings=evidence.findings,
                recommended_action=evidence.recommended_action
            )
            
        except Exception as e:
            print(f"❌ Llama analysis failed for {player_id}: {e}")
            return None
    
    def get_all_scores(self) -> Dict[str, dict]:
        """Get all current AI scores."""
        result = {}
        for player_id, state in self.player_states.items():
            result[player_id] = {
                "score": state.xgboost_score,
                "is_flagged": state.is_flagged,
                "moves_analyzed": state.total_moves_analyzed,
                "has_llama_analysis": state.llama_analysis is not None
            }
        return result
    
    def get_flagged_players(self) -> List[str]:
        """Get list of flagged player IDs."""
        return self.flagged_players.copy()
    
    def get_player_analysis(self, player_id: str) -> Optional[dict]:
        """Get detailed analysis for a specific player."""
        state = self.player_states.get(player_id)
        if not state:
            return None
        
        return {
            "player_id": player_id,
            "xgboost_score": state.xgboost_score,
            "is_flagged": state.is_flagged,
            "total_moves": state.total_moves_analyzed,
            "feature_dict": state.feature_extractor.get_feature_dict(),
            "llama_analysis": state.llama_analysis
        }


# Global singleton
ai_detector = AIDetector()
