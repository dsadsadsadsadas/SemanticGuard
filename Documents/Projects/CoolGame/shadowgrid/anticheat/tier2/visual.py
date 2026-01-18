"""
ShadowGrid Visual Analyzer

Uses Groq API with Llama 3.1 for visual analysis of gameplay replays.
"""

from __future__ import annotations
import os
import json
import base64
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass
import io

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    Groq = None


@dataclass
class VisualEvidence:
    """Evidence from visual analysis."""
    replay_id: str
    player_id: str
    start_tick: int
    end_tick: int
    
    # Analysis results
    suspicion_level: str  # 'low', 'medium', 'high', 'certain'
    confidence: float     # 0-1
    findings: List[str]
    reasoning: str
    
    # Recommended action
    recommended_action: str  # 'clear', 'monitor', 'review', 'ban'


# Analysis prompts for different cheat types
ANALYSIS_PROMPTS = {
    'wallhack': """Analyze this gameplay sequence for wallhack/ESP indicators:
- Does the player move directly toward hidden objectives without exploring?
- Do they avoid lava that should be invisible to them?
- Do they pre-aim or pre-position for things outside their fog of war?
- Is their pathing suspiciously optimal for the full map layout?

Player ID: {player_id}
Sequence: Ticks {start_tick} to {end_tick}
Frame data: {frame_data}

Provide your analysis with:
1. SUSPICION_LEVEL: low/medium/high/certain
2. CONFIDENCE: 0.0-1.0
3. FINDINGS: List specific suspicious behaviors
4. REASONING: Explain your conclusion
5. RECOMMENDED_ACTION: clear/monitor/review/ban""",

    'speedhack': """Analyze this gameplay sequence for speedhack indicators:
- Does the player move faster than physically possible?
- Are there sudden position changes (teleportation)?
- Is their input rate inhuman?
- Do they cover more ground than expected between ticks?

Player ID: {player_id}
Sequence: Ticks {start_tick} to {end_tick}
Frame data: {frame_data}

Provide your analysis with:
1. SUSPICION_LEVEL: low/medium/high/certain
2. CONFIDENCE: 0.0-1.0
3. FINDINGS: List specific suspicious behaviors
4. REASONING: Explain your conclusion
5. RECOMMENDED_ACTION: clear/monitor/review/ban""",

    'aimbot': """Analyze this gameplay sequence for aimbot/automation indicators:
- Are direction changes too snappy or mechanical?
- Is timing between inputs unnaturally regular?
- Do they achieve perfect movement patterns?
- Is there evidence of macro/scripted behavior?

Player ID: {player_id}
Sequence: Ticks {start_tick} to {end_tick}
Frame data: {frame_data}

Provide your analysis with:
1. SUSPICION_LEVEL: low/medium/high/certain
2. CONFIDENCE: 0.0-1.0
3. FINDINGS: List specific suspicious behaviors
4. REASONING: Explain your conclusion
5. RECOMMENDED_ACTION: clear/monitor/review/ban""",

    'general': """Analyze this gameplay sequence for any cheating indicators:
- Movement anomalies (speed, teleportation)
- Knowledge anomalies (knowing hidden information)
- Behavioral anomalies (inhuman timing, perfect patterns)
- Any other suspicious behaviors

Player ID: {player_id}
Sequence: Ticks {start_tick} to {end_tick}
Frame data: {frame_data}

Provide your analysis with:
1. SUSPICION_LEVEL: low/medium/high/certain
2. CONFIDENCE: 0.0-1.0
3. FINDINGS: List specific suspicious behaviors
4. REASONING: Explain your conclusion
5. RECOMMENDED_ACTION: clear/monitor/review/ban"""
}


class VisualAnalyzer:
    """
    Analyzes gameplay replays using Llama 3.1 via Groq.
    
    Takes replay frames and uses LLM reasoning to identify
    visual patterns that indicate cheating.
    """
    
    # Groq model to use
    MODEL = "llama-3.1-70b-versatile"
    
    def __init__(self, api_key: Optional[str] = None):
        if not GROQ_AVAILABLE:
            raise ImportError(
                "Groq package is required for visual analysis. "
                "Install with: pip install groq"
            )
        
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable must be set"
            )
        
        self.client = Groq(api_key=self.api_key)
    
    def analyze_replay_segment(
        self,
        replay_id: str,
        player_id: str,
        frames: List[dict],
        cheat_type: str = 'general'
    ) -> VisualEvidence:
        """
        Analyze a segment of replay for cheating.
        
        Args:
            replay_id: ID of the replay
            player_id: Player being analyzed
            frames: List of frame dicts with game state
            cheat_type: Type of cheat to look for
            
        Returns:
            VisualEvidence with analysis results
        """
        if not frames:
            return VisualEvidence(
                replay_id=replay_id,
                player_id=player_id,
                start_tick=0,
                end_tick=0,
                suspicion_level='low',
                confidence=0.0,
                findings=[],
                reasoning="No frames to analyze",
                recommended_action='clear'
            )
        
        start_tick = frames[0].get('tick', 0)
        end_tick = frames[-1].get('tick', 0)
        
        # Prepare frame data as text (LLM can't see images directly)
        frame_summary = self._summarize_frames(frames, player_id)
        
        # Get appropriate prompt
        prompt_template = ANALYSIS_PROMPTS.get(cheat_type, ANALYSIS_PROMPTS['general'])
        prompt = prompt_template.format(
            player_id=player_id,
            start_tick=start_tick,
            end_tick=end_tick,
            frame_data=frame_summary
        )
        
        # Call Groq API
        try:
            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert anti-cheat analyst. "
                            "Analyze gameplay data and provide structured assessments. "
                            "Be thorough but fair - false positives harm innocent players."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for consistency
                max_tokens=1000
            )
            
            analysis_text = response.choices[0].message.content
            return self._parse_analysis(
                analysis_text, replay_id, player_id, start_tick, end_tick
            )
        
        except Exception as e:
            return VisualEvidence(
                replay_id=replay_id,
                player_id=player_id,
                start_tick=start_tick,
                end_tick=end_tick,
                suspicion_level='low',
                confidence=0.0,
                findings=[],
                reasoning=f"Analysis failed: {str(e)}",
                recommended_action='review'  # Manual review on failure
            )
    
    def _summarize_frames(
        self,
        frames: List[dict],
        player_id: str
    ) -> str:
        """Summarize frames into text for LLM analysis."""
        lines = []
        prev_pos = None
        prev_tick = None
        
        for i, frame in enumerate(frames):
            tick = frame.get('tick', i)
            player_states = frame.get('player_states', {})
            
            player_state = player_states.get(player_id, {})
            x = player_state.get('x', 0)
            y = player_state.get('y', 0)
            
            # Calculate movement
            if prev_pos:
                dx = x - prev_pos[0]
                dy = y - prev_pos[1]
                distance = abs(dx) + abs(dy)
                ticks_elapsed = tick - prev_tick if prev_tick else 1
                speed = distance / max(ticks_elapsed, 1)
                
                if distance > 0:
                    lines.append(
                        f"T{tick}: pos({x},{y}) moved({dx},{dy}) speed={speed:.2f}"
                    )
            else:
                lines.append(f"T{tick}: start pos({x},{y})")
            
            # Check for inputs in this frame
            inputs = frame.get('inputs', [])
            player_inputs = [inp for inp in inputs if inp.get('player_id') == player_id]
            if player_inputs:
                for inp in player_inputs:
                    direction = inp.get('direction', 0)
                    lines.append(f"  INPUT: direction={direction}")
            
            prev_pos = (x, y)
            prev_tick = tick
        
        # Limit output size
        if len(lines) > 50:
            lines = lines[:25] + ['...'] + lines[-25:]
        
        return '\n'.join(lines)
    
    def _parse_analysis(
        self,
        text: str,
        replay_id: str,
        player_id: str,
        start_tick: int,
        end_tick: int
    ) -> VisualEvidence:
        """Parse LLM response into structured evidence."""
        # Default values
        suspicion_level = 'low'
        confidence = 0.5
        findings = []
        reasoning = text
        recommended_action = 'review'
        
        # Try to parse structured response
        lines = text.split('\n')
        
        for line in lines:
            line_lower = line.lower()
            
            if 'suspicion_level' in line_lower or 'suspicion level' in line_lower:
                if 'certain' in line_lower:
                    suspicion_level = 'certain'
                elif 'high' in line_lower:
                    suspicion_level = 'high'
                elif 'medium' in line_lower:
                    suspicion_level = 'medium'
                else:
                    suspicion_level = 'low'
            
            elif 'confidence' in line_lower:
                # Extract number
                import re
                numbers = re.findall(r'[0-9]*\.?[0-9]+', line)
                if numbers:
                    confidence = min(1.0, max(0.0, float(numbers[0])))
            
            elif 'findings' in line_lower or 'finding' in line_lower:
                # Next lines are likely findings
                pass
            
            elif line.strip().startswith('-') or line.strip().startswith('•'):
                findings.append(line.strip().lstrip('-•').strip())
            
            elif 'recommended_action' in line_lower or 'recommended action' in line_lower:
                if 'ban' in line_lower:
                    recommended_action = 'ban'
                elif 'clear' in line_lower:
                    recommended_action = 'clear'
                elif 'monitor' in line_lower:
                    recommended_action = 'monitor'
                else:
                    recommended_action = 'review'
            
            elif 'reasoning' in line_lower:
                # Next content is reasoning
                idx = text.find(line) + len(line)
                remaining = text[idx:].split('\n')[0:3]
                reasoning = ' '.join(remaining).strip()
        
        return VisualEvidence(
            replay_id=replay_id,
            player_id=player_id,
            start_tick=start_tick,
            end_tick=end_tick,
            suspicion_level=suspicion_level,
            confidence=confidence,
            findings=findings[:10],  # Limit findings
            reasoning=reasoning[:500],  # Limit reasoning
            recommended_action=recommended_action
        )
    
    def batch_analyze(
        self,
        segments: List[Tuple[str, str, List[dict]]],
        cheat_type: str = 'general'
    ) -> List[VisualEvidence]:
        """
        Analyze multiple replay segments.
        
        Args:
            segments: List of (replay_id, player_id, frames) tuples
            cheat_type: Type of cheat to look for
            
        Returns:
            List of VisualEvidence
        """
        results = []
        
        for replay_id, player_id, frames in segments:
            result = self.analyze_replay_segment(
                replay_id, player_id, frames, cheat_type
            )
            results.append(result)
        
        return results


class MockVisualAnalyzer:
    """
    Mock analyzer for testing without Groq API.
    """
    
    def __init__(self):
        pass
    
    def analyze_replay_segment(
        self,
        replay_id: str,
        player_id: str,
        frames: List[dict],
        cheat_type: str = 'general'
    ) -> VisualEvidence:
        """Mock analysis based on frame data."""
        if not frames:
            return VisualEvidence(
                replay_id=replay_id,
                player_id=player_id,
                start_tick=0,
                end_tick=0,
                suspicion_level='low',
                confidence=0.0,
                findings=[],
                reasoning="No frames",
                recommended_action='clear'
            )
        
        # Simple heuristic analysis
        teleports = 0
        max_speed = 0
        
        prev_pos = None
        for frame in frames:
            player_states = frame.get('player_states', {})
            player_state = player_states.get(player_id, {})
            x = player_state.get('x', 0)
            y = player_state.get('y', 0)
            
            if prev_pos:
                dist = abs(x - prev_pos[0]) + abs(y - prev_pos[1])
                max_speed = max(max_speed, dist)
                if dist > 2:
                    teleports += 1
            
            prev_pos = (x, y)
        
        # Make decision
        if teleports > 0:
            return VisualEvidence(
                replay_id=replay_id,
                player_id=player_id,
                start_tick=frames[0].get('tick', 0),
                end_tick=frames[-1].get('tick', 0),
                suspicion_level='high',
                confidence=0.9,
                findings=[f"Detected {teleports} teleportation events"],
                reasoning="Position changed by more than 2 tiles in single tick",
                recommended_action='ban'
            )
        
        return VisualEvidence(
            replay_id=replay_id,
            player_id=player_id,
            start_tick=frames[0].get('tick', 0),
            end_tick=frames[-1].get('tick', 0),
            suspicion_level='low',
            confidence=0.8,
            findings=[],
            reasoning="No suspicious patterns detected",
            recommended_action='clear'
        )
