"""
ShadowGrid Match Manager

Handles match lifecycle, case recording, and AI inspection at game end.
"""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from ..database import db_manager, Match, MatchCase
from sqlalchemy import select, desc


@dataclass
class PlayerMatchData:
    """Runtime data for a player in the current match."""
    player_id: str
    is_cheater: bool = False  # Ground truth
    cheat_type: Optional[str] = None
    total_moves: int = 0
    ai_score: float = 0.0
    ai_reasoning: Optional[str] = None
    features: Optional[Dict[str, float]] = None


class MatchManager:
    """
    Manages match lifecycle and case recording.
    
    Flow:
    1. start_match() - Called when game starts
    2. register_player() - Called for each connecting player
    3. update_player() - Called during game with stats
    4. finalize_match() - Called at game end, triggers AI inspection
    """
    
    def __init__(self):
        self.current_match_id: Optional[str] = None
        self.match_started_at: Optional[datetime] = None
        self.players: Dict[str, PlayerMatchData] = {}
    
    def start_match(self) -> str:
        """Start a new match. Returns match_id."""
        self.current_match_id = f"match_{uuid.uuid4().hex[:12]}"
        self.match_started_at = datetime.utcnow()
        self.players = {}
        print(f"🎮 Match started: {self.current_match_id}")
        return self.current_match_id
    
    def register_player(
        self,
        player_id: str,
        is_cheater: bool = False,
        cheat_type: Optional[str] = None
    ) -> None:
        """Register a player in the current match."""
        if not self.current_match_id:
            self.start_match()
        
        self.players[player_id] = PlayerMatchData(
            player_id=player_id,
            is_cheater=is_cheater,
            cheat_type=cheat_type
        )
        print(f"📝 Player registered: {player_id} (cheater={is_cheater})")
    
    def update_player(
        self,
        player_id: str,
        total_moves: Optional[int] = None,
        ai_score: Optional[float] = None,
        ai_reasoning: Optional[str] = None,
        features: Optional[Dict[str, float]] = None
    ) -> None:
        """Update player stats during match."""
        if player_id not in self.players:
            return
        
        player = self.players[player_id]
        if total_moves is not None:
            player.total_moves = total_moves
        if ai_score is not None:
            player.ai_score = ai_score
        if ai_reasoning is not None:
            player.ai_reasoning = ai_reasoning
        if features is not None:
            player.features = features
    
    async def finalize_match(self, ai_detector=None) -> Optional[str]:
        """
        Finalize the match and save to database.
        
        - Triggers AI inspection for each player
        - Computes RL rewards
        - Saves Match and MatchCases to DB
        
        Returns match_id if successful.
        """
        if not self.current_match_id or not self.players:
            return None
        
        match_id = self.current_match_id
        ended_at = datetime.utcnow()
        duration = (ended_at - self.match_started_at).total_seconds() if self.match_started_at else 0
        
        # Count stats
        player_count = len(self.players)
        cheater_count = sum(1 for p in self.players.values() if p.is_cheater)
        
        # Run final AI analysis if detector provided
        if ai_detector:
            for pid, player in self.players.items():
                analysis = ai_detector.get_player_analysis(pid)
                if analysis:
                    player.ai_score = analysis.get('xgboost_score', 0.0)
                    if analysis.get('llama_analysis'):
                        player.ai_reasoning = analysis['llama_analysis'].get('reasoning')
                    player.features = analysis.get('feature_dict')
        
        # Compute verdicts and rewards
        correct = 0
        incorrect = 0
        total_reward = 0.0
        
        cases_data = []
        for pid, player in self.players.items():
            # AI thinks they're cheating if score > 30%
            ai_verdict = player.ai_score >= 30.0
            was_correct = (ai_verdict == player.is_cheater)
            
            # RL Reward: +1 correct, -1 incorrect
            reward = 1.0 if was_correct else -1.0
            total_reward += reward
            
            if was_correct:
                correct += 1
            else:
                incorrect += 1
            
            cases_data.append({
                'player_id': pid,
                'is_cheater': player.is_cheater,
                'cheat_type': player.cheat_type,
                'ai_score': player.ai_score,
                'ai_verdict': ai_verdict,
                'ai_confidence': player.ai_score / 100.0,
                'ai_reasoning': player.ai_reasoning,
                'was_correct': was_correct,
                'rl_reward': reward,
                'total_moves': player.total_moves,
                'features_snapshot': player.features
            })
        
        accuracy = correct / player_count if player_count > 0 else 0.0
        
        # Save to database
        try:
            async with db_manager.session_factory() as session:
                # Create Match
                match = Match(
                    match_id=match_id,
                    started_at=self.match_started_at,
                    ended_at=ended_at,
                    duration_seconds=duration,
                    player_count=player_count,
                    cheater_count=cheater_count,
                    correct_detections=correct,
                    incorrect_detections=incorrect,
                    detection_accuracy=accuracy,
                    rl_reward_total=total_reward,
                    rl_trained=False
                )
                session.add(match)
                
                # Create MatchCases
                for case_data in cases_data:
                    case = MatchCase(
                        match_id=match_id,
                        **case_data
                    )
                    session.add(case)
                
                await session.commit()
                
            print(f"✅ Match finalized: {match_id}")
            print(f"   Players: {player_count}, Cheaters: {cheater_count}")
            print(f"   AI Accuracy: {accuracy*100:.1f}% ({correct}/{player_count})")
            print(f"   RL Reward: {total_reward:+.1f}")
            
        except Exception as e:
            print(f"❌ Failed to save match: {e}")
            return None
        
        # Reset state
        self.current_match_id = None
        self.match_started_at = None
        self.players = {}
        
        return match_id
    
    async def get_match_history(self, limit: int = 50) -> List[dict]:
        """Get recent matches."""
        try:
            async with db_manager.session_factory() as session:
                result = await session.execute(
                    select(Match).order_by(desc(Match.ended_at)).limit(limit)
                )
                matches = result.scalars().all()
                
                return [
                    {
                        'match_id': m.match_id,
                        'started_at': m.started_at.isoformat() if m.started_at else None,
                        'ended_at': m.ended_at.isoformat() if m.ended_at else None,
                        'duration_seconds': m.duration_seconds,
                        'player_count': m.player_count,
                        'cheater_count': m.cheater_count,
                        'correct_detections': m.correct_detections,
                        'detection_accuracy': m.detection_accuracy,
                        'rl_reward_total': m.rl_reward_total,
                        'rl_trained': m.rl_trained
                    }
                    for m in matches
                ]
        except Exception as e:
            print(f"❌ Failed to get match history: {e}")
            return []
    
    async def get_match_cases(self, match_id: str) -> List[dict]:
        """Get all cases for a specific match."""
        try:
            async with db_manager.session_factory() as session:
                result = await session.execute(
                    select(MatchCase).where(MatchCase.match_id == match_id)
                )
                cases = result.scalars().all()
                
                return [
                    {
                        'player_id': c.player_id,
                        'is_cheater': c.is_cheater,
                        'cheat_type': c.cheat_type,
                        'ai_score': c.ai_score,
                        'ai_verdict': c.ai_verdict,
                        'ai_confidence': c.ai_confidence,
                        'ai_reasoning': c.ai_reasoning,
                        'was_correct': c.was_correct,
                        'rl_reward': c.rl_reward,
                        'total_moves': c.total_moves
                    }
                    for c in cases
                ]
        except Exception as e:
            print(f"❌ Failed to get match cases: {e}")
            return []


# Global singleton
match_manager = MatchManager()
