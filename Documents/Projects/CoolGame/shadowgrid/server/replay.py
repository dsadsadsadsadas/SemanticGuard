"""
ShadowGrid Replay Recorder

Records game sessions for anti-cheat analysis and review.
"""

from __future__ import annotations
import json
import time
import gzip
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from ..game.lockstep import TickState, PlayerInput


@dataclass
class ReplayFrame:
    """A single frame of replay data."""
    tick: int
    timestamp: float
    grid_state: List[List[int]]
    player_states: Dict[str, dict]
    inputs: List[dict]
    events: List[dict] = field(default_factory=list)


@dataclass
class ReplayMetadata:
    """Metadata for a replay file."""
    replay_id: str
    game_start: float
    game_end: float
    player_ids: List[str]
    total_ticks: int
    grid_size: tuple
    version: str = "1.0"


class ReplayRecorder:
    """
    Records game sessions for later analysis.
    
    Stores:
    - Complete game state per tick
    - All player inputs
    - Events (crystals collected, deaths, etc.)
    - Validation flags
    """
    
    def __init__(self, replay_dir: str = "data/replays"):
        self.replay_dir = Path(replay_dir)
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_replay_id: Optional[str] = None
        self.frames: List[ReplayFrame] = []
        self.pending_inputs: List[dict] = []
        self.pending_events: List[dict] = []
        self.recording: bool = False
        self.start_time: float = 0.0
    
    def start_recording(self, replay_id: str) -> None:
        """Start recording a new replay."""
        self.current_replay_id = replay_id
        self.frames = []
        self.pending_inputs = []
        self.pending_events = []
        self.recording = True
        self.start_time = time.time()
    
    def stop_recording(self) -> Optional[str]:
        """Stop recording and save replay."""
        if not self.recording:
            return None
        
        self.recording = False
        
        if not self.frames:
            return None
        
        # Create metadata
        metadata = ReplayMetadata(
            replay_id=self.current_replay_id,
            game_start=self.start_time,
            game_end=time.time(),
            player_ids=list(set(
                pid for frame in self.frames
                for pid in frame.player_states.keys()
            )),
            total_ticks=len(self.frames),
            grid_size=(
                len(self.frames[0].grid_state[0]) if self.frames[0].grid_state else 0,
                len(self.frames[0].grid_state) if self.frames[0].grid_state else 0
            )
        )
        
        # Save replay
        filepath = self._save_replay(metadata)
        
        return str(filepath)
    
    def record_tick(
        self,
        tick_state: TickState,
        grid_state: List[List[int]]
    ) -> None:
        """Record a game tick."""
        if not self.recording:
            return
        
        frame = ReplayFrame(
            tick=tick_state.tick,
            timestamp=time.time(),
            grid_state=grid_state,
            player_states=tick_state.player_states,
            inputs=self.pending_inputs.copy(),
            events=self.pending_events.copy()
        )
        
        self.frames.append(frame)
        self.pending_inputs.clear()
        self.pending_events.clear()
    
    def record_input(self, input_data: dict) -> None:
        """Record a player input."""
        if self.recording:
            self.pending_inputs.append({
                **input_data,
                'recorded_at': time.time()
            })
    
    def record_event(self, event_type: str, data: dict) -> None:
        """Record a game event."""
        if self.recording:
            self.pending_events.append({
                'type': event_type,
                'data': data,
                'timestamp': time.time()
            })
    
    def _save_replay(self, metadata: ReplayMetadata) -> Path:
        """Save replay to compressed JSON file."""
        replay_data = {
            'metadata': {
                'replay_id': metadata.replay_id,
                'game_start': metadata.game_start,
                'game_end': metadata.game_end,
                'player_ids': metadata.player_ids,
                'total_ticks': metadata.total_ticks,
                'grid_size': metadata.grid_size,
                'version': metadata.version
            },
            'frames': [
                {
                    'tick': f.tick,
                    'timestamp': f.timestamp,
                    'grid_state': f.grid_state,
                    'player_states': f.player_states,
                    'inputs': f.inputs,
                    'events': f.events
                }
                for f in self.frames
            ]
        }
        
        filepath = self.replay_dir / f"{metadata.replay_id}.json.gz"
        
        with gzip.open(filepath, 'wt', encoding='utf-8') as f:
            json.dump(replay_data, f)
        
        return filepath
    
    @staticmethod
    def load_replay(filepath: str) -> Dict[str, Any]:
        """Load a replay from file."""
        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            return json.load(f)
    
    def get_frames_for_player(
        self,
        player_id: str,
        start_tick: int = 0,
        end_tick: Optional[int] = None
    ) -> List[ReplayFrame]:
        """Get replay frames for a specific player."""
        result = []
        
        for frame in self.frames:
            if frame.tick < start_tick:
                continue
            if end_tick and frame.tick > end_tick:
                break
            if player_id in frame.player_states:
                result.append(frame)
        
        return result


class ReplayAnalyzer:
    """
    Analyzes replays for anti-cheat evidence.
    
    Extracts:
    - Movement patterns
    - Suspicious timestamps
    - Impossible actions
    - Knowledge anomalies (seeing through fog)
    """
    
    def __init__(self, replay_data: Dict[str, Any]):
        self.metadata = replay_data['metadata']
        self.frames = replay_data['frames']
    
    def analyze_player(self, player_id: str) -> dict:
        """Analyze a specific player's behavior in the replay."""
        player_frames = [
            f for f in self.frames
            if player_id in f.get('player_states', {})
        ]
        
        if not player_frames:
            return {'error': 'Player not found in replay'}
        
        analysis = {
            'player_id': player_id,
            'total_frames': len(player_frames),
            'movement_analysis': self._analyze_movement(player_id, player_frames),
            'timing_analysis': self._analyze_timing(player_id, player_frames),
            'knowledge_analysis': self._analyze_knowledge(player_id, player_frames)
        }
        
        return analysis
    
    def _analyze_movement(self, player_id: str, frames: List[dict]) -> dict:
        """Analyze movement patterns."""
        positions = []
        velocities = []
        
        for i, frame in enumerate(frames):
            ps = frame['player_states'].get(player_id, {})
            pos = (ps.get('x', 0), ps.get('y', 0))
            positions.append(pos)
            
            if i > 0:
                prev_pos = positions[-2]
                dx = pos[0] - prev_pos[0]
                dy = pos[1] - prev_pos[1]
                velocities.append((dx, dy))
        
        # Calculate statistics
        total_distance = sum(
            abs(v[0]) + abs(v[1]) for v in velocities
        )
        
        teleports = sum(
            1 for v in velocities
            if abs(v[0]) > 1 or abs(v[1]) > 1
        )
        
        return {
            'total_distance': total_distance,
            'teleport_count': teleports,
            'suspicious': teleports > 0
        }
    
    def _analyze_timing(self, player_id: str, frames: List[dict]) -> dict:
        """Analyze input timing."""
        inputs = []
        
        for frame in frames:
            for inp in frame.get('inputs', []):
                if inp.get('player_id') == player_id:
                    inputs.append(inp)
        
        if len(inputs) < 2:
            return {'intervals': [], 'suspicious': False}
        
        intervals = []
        for i in range(1, len(inputs)):
            t1 = inputs[i-1].get('recorded_at', 0)
            t2 = inputs[i].get('recorded_at', 0)
            intervals.append((t2 - t1) * 1000)  # ms
        
        # Check for inhuman timing
        suspicious_count = sum(1 for i in intervals if i < 20)  # <20ms
        
        return {
            'total_inputs': len(inputs),
            'avg_interval_ms': sum(intervals) / len(intervals) if intervals else 0,
            'min_interval_ms': min(intervals) if intervals else 0,
            'suspicious_intervals': suspicious_count,
            'suspicious': suspicious_count > len(intervals) * 0.1
        }
    
    def _analyze_knowledge(self, player_id: str, frames: List[dict]) -> dict:
        """Analyze for knowledge beyond fog of war."""
        # This would require visibility calculations per frame
        # Simplified version: look for moves toward hidden crystals
        
        return {
            'analyzed': False,
            'requires_full_grid_state': True
        }
    
    def extract_clip(
        self,
        start_tick: int,
        end_tick: int
    ) -> List[dict]:
        """Extract a clip for expert review."""
        return [
            f for f in self.frames
            if start_tick <= f.get('tick', 0) <= end_tick
        ]
