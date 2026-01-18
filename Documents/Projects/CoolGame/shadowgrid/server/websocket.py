"""
ShadowGrid WebSocket Handler

Real-time game communication with lockstep protocol.
"""

from __future__ import annotations
import asyncio
import json
import time
from typing import Dict, Set, Optional
from dataclasses import dataclass
from fastapi import WebSocket, WebSocketDisconnect

from ..game.world import Grid, GridConfig
from ..game.player import Player
from ..game.lockstep import (
    GameState, LockstepProtocol, PlayerInput,
    InputType, ValidationResult
)
from ..game.constants import Direction, DEFAULT_TICK_CONFIG
from .validator import InputValidator
from .ai_detector import ai_detector
from .match_manager import match_manager


@dataclass
class ConnectedClient:
    """Represents a connected client."""
    websocket: WebSocket
    player_id: str
    connected_at: float
    last_ping: float = 0.0
    latency_ms: float = 0.0


class GameWebSocket:
    """
    WebSocket manager for real-time game communication.
    
    Handles:
    - Player connections/disconnections
    - Input receiving and broadcasting
    - State synchronization
    - Tick loop management
    """
    
    def __init__(self):
        self.clients: Dict[str, ConnectedClient] = {}
        self.game_state: Optional[GameState] = None
        self.validator: InputValidator = InputValidator()
        self.tick_task: Optional[asyncio.Task] = None
        self.running: bool = False
        self.active_sessions: Dict[str, str] = {}  # player_id -> session_id
    
    def create_game(self, config: GridConfig = GridConfig()) -> None:
        """Create a new game instance."""
        grid = Grid.generate(config)
        self.game_state = GameState(grid)
        self.validator = InputValidator()
    
    async def connect(self, websocket: WebSocket, player_id: str) -> bool:
        """Handle new client connection."""
        await websocket.accept()
        
        # Check if game exists
        if not self.game_state:
            self.create_game()
        
        # Create client entry
        self.clients[player_id] = ConnectedClient(
            websocket=websocket,
            player_id=player_id,
            connected_at=time.time(),
            last_ping=time.time()
        )
        print(f"✅ Added {player_id} to clients. Total clients: {len(self.clients)}")
        print(f"   Client IDs: {list(self.clients.keys())}")
        
        # Create player in game
        player = Player(player_id=player_id)
        self.game_state.add_player(player)
        
        # Register with AI detector
        ai_detector.register_player(player_id)
        
        # Register with match manager (ground truth from player_id prefix)
        is_cheater = player_id.startswith('Sus') or player_id.startswith('Cheater')
        match_manager.register_player(player_id, is_cheater=is_cheater)
        
        # Database: Create session
        try:
            from ..database import db_manager, PlayerRepository, SessionRepository
            async with db_manager.session_factory() as session:
                player_repo = PlayerRepository(session)
                session_repo = SessionRepository(session)
                
                # Ensure player exists
                await player_repo.get_or_create(player_id)
                await player_repo.update_last_seen(player_id)
                
                # Create game session
                db_session = await session_repo.create(player_id)
                self.active_sessions[player_id] = db_session.session_id
                
                await session.commit()
                print(f"Recorded session {db_session.session_id} for {player_id}")
        except Exception as e:
            print(f"Database error on connect: {e}")
        
        # Send initial state
        await self._send_initial_state(player_id)
        
        # Start tick loop if not running
        if not self.running:
            self.running = True
            self.tick_task = asyncio.create_task(self._tick_loop())
        
        # Broadcast join
        await self._broadcast({
            'type': 'PLAYER_JOINED',
            'player_id': player_id,
            'player_count': len(self.clients)
        }, exclude={player_id})
        
        return True
    
    async def disconnect(self, player_id: str) -> None:
        """Handle client disconnection."""
        client = self.clients.pop(player_id, None)
        
        # Get session ID
        session_id = self.active_sessions.pop(player_id, None)
        
        if self.game_state:
            player = self.game_state.players.get(player_id)
            
            # Database: End session and save stats
            if player and session_id:
                # Final Audit: Force analysis before clearing state
                # This catches cheaters who disconnect immediately after suspicious moves
                try:
                    await ai_detector.analyze_now(player_id)
                    
                    # [FIX] Sync final AI scores to match_manager before finalization
                    ai_data = ai_detector.get_player_analysis(player_id)
                    if ai_data:
                        from .match_manager import match_manager
                        match_manager.update_player(
                            player_id,
                            total_moves=player.stats.total_moves,
                            ai_score=ai_data.get('xgboost_score', 0.0)
                        )
                        print(f"[SYNC] Updated match_manager for {player_id}: AI Score={ai_data.get('xgboost_score', 0.0):.1f}%")
                except Exception as e:
                    print(f"Failed to run final audit: {e}")
                    
                try:
                    from ..database import db_manager, SessionRepository, PlayerRepository
                    async with db_manager.session_factory() as session:
                        session_repo = SessionRepository(session)
                        player_repo = PlayerRepository(session)
                        
                        await session_repo.end_session(
                            session_id,
                            crystals=player.stats.crystals_collected,
                            deaths=player.stats.deaths,
                            moves=player.stats.total_moves,
                            score=player.score
                        )
                        
                        await player_repo.update_session_stats(
                            player_id,
                            session_duration=0.0,  # Logic handles this
                            moves=player.stats.total_moves,
                            crystals=player.stats.crystals_collected,
                            deaths=player.stats.deaths
                        )
                        
                        # Save replay data if available
                        if hasattr(player.stats, 'movement_history'):
                            replay_data = [
                                {
                                    't': m.timestamp,
                                    'x': m.to_pos[0],
                                    'y': m.to_pos[1],
                                    'd': m.direction
                                }
                                for m in player.stats.movement_history
                            ]
                            await session_repo.save_replay(session_id, replay_data)
                        
                        await session.commit()
                        print(f"Stats saved for session {session_id}")
                except Exception as e:
                    print(f"Database error on disconnect: {e}")
            
            self.game_state.remove_player(player_id)
        
        self.validator.clear_player(player_id)
        
        # Update match manager with final player stats before unregistering
        if player:
            ai_state = ai_detector.get_player_analysis(player_id)
            ai_score = ai_state.get('xgboost_score', 0.0) if ai_state else 0.0
            features = ai_state.get('feature_dict') if ai_state else None
            
            # Get actual detection indicators
            indicators = {}
            if ai_state and 'feature_dict' in ai_state:
                fd = ai_state['feature_dict']
                indicators = {
                    'speed_violations': fd.get('speed_violation_count', 0),
                    'teleports': fd.get('teleport_count', 0),
                    'input_freq': fd.get('input_frequency', 0),
                    'input_regularity': fd.get('input_regularity_std', 0),
                }
            
            # Generate real reasoning from indicators
            reasoning_parts = []
            
            sv = indicators.get('speed_violations', 0)
            if sv > 10:
                reasoning_parts.append(f"❗ {sv} speed violations (inputs < 150ms)")
            elif sv > 0:
                reasoning_parts.append(f"⚠️ {sv} speed violations")
            else:
                reasoning_parts.append("✅ No speed violations")
            
            tp = indicators.get('teleports', 0)
            if tp > 0:
                reasoning_parts.append(f"🚨 {tp} teleport attempts")
            
            freq = indicators.get('input_freq', 0)
            if freq > 5:
                reasoning_parts.append(f"⚡ High input rate: {freq:.1f}/sec")
            elif freq > 0:
                reasoning_parts.append(f"📊 Input rate: {freq:.1f}/sec")
            
            reg = indicators.get('input_regularity', 0)
            if reg < 20 and freq > 3:
                reasoning_parts.append("🤖 Suspiciously consistent timing (bot-like)")
            
            ai_reasoning = " | ".join(reasoning_parts) if reasoning_parts else "No data available"
            
            match_manager.update_player(
                player_id,
                total_moves=player.stats.total_moves,
                ai_score=ai_score,
                ai_reasoning=ai_reasoning,
                features=features
            )
        
        ai_detector.unregister_player(player_id)
        
        # Broadcast leave
        await self._broadcast({
            'type': 'PLAYER_LEFT',
            'player_id': player_id,
            'player_count': len(self.clients)
        })
        
        # Stop tick loop if no clients
        if not self.clients and self.running:
            self.running = False
            if self.tick_task:
                self.tick_task.cancel()
            # Finalize match when all players leave
            asyncio.create_task(match_manager.finalize_match(ai_detector))
    
    async def handle_message(self, player_id: str, message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'INPUT':
                await self._handle_input(player_id, data)
            elif msg_type == 'PING':
                await self._handle_ping(player_id, data)
            elif msg_type == 'SYNC_REQUEST':
                await self._handle_sync_request(player_id, data)
            elif msg_type == 'RESTART':
                await self._handle_restart(player_id)
            else:
                await self._send_to_player(player_id, {
                    'type': 'ERROR',
                    'message': f'Unknown message type: {msg_type}'
                })
        
        except json.JSONDecodeError:
            await self._send_to_player(player_id, {
                'type': 'ERROR',
                'message': 'Invalid JSON'
            })
    
    async def _handle_input(self, player_id: str, data: dict) -> None:
        """Handle player input message."""
        if not self.game_state:
            return
        
        # Decode input
        player_input = LockstepProtocol.decode_input({
            **data,
            'player_id': player_id
        })
        
        # Get current player position for validation
        player = self.game_state.players.get(player_id)
        if not player:
            return
        
        current_pos = (player.x, player.y)
        
        # Validate input
        validation = self.validator.validate_input(
            player_input,
            current_pos,
            self.game_state.current_tick
        )
        
        if not validation.valid:
            await self._send_to_player(player_id, {
                'type': 'INPUT_REJECTED',
                'reason': validation.reason,
                'severity': validation.severity
            })
            
            # If severe, trigger resync
            if validation.severity >= 3:
                await self._send_resync(player_id)
            return
        
        # Queue input for processing
        result = self.game_state.queue_input(player_input)
        
        # Debug: Log when input is queued
        if result.valid:
            buf_len = len(self.game_state.input_buffers.get(player_id, []))
            print(f"📥 INPUT QUEUED: {player_id} dir={player_input.direction} | Buffer size: {buf_len}", flush=True)
        
        if not result.valid:
            await self._send_to_player(player_id, {
                'type': 'INPUT_REJECTED',
                'reason': result.reason
            })
    
    async def _handle_ping(self, player_id: str, data: dict) -> None:
        """Handle ping message for latency measurement."""
        client = self.clients.get(player_id)
        if client:
            client.last_ping = time.time()
            client.latency_ms = data.get('latency', 0)
        
        await self._send_to_player(player_id, {
            'type': 'PONG',
            'server_time': time.time(),
            'tick': self.game_state.current_tick if self.game_state else 0
        })
    
    async def _handle_sync_request(self, player_id: str, data: dict) -> None:
        """Handle resync request from client."""
        await self._send_resync(player_id)
    
    async def _handle_restart(self, player_id: str) -> None:
        """Handle player restart request."""
        if not self.game_state:
            return
        
        player = self.game_state.players.get(player_id)
        if not player:
            return
        
        # Only allow restart if dead
        if player.alive:
            return
        
        # Respawn player
        player.alive = True
        player.health = 100
        player.score = 0
        player.stats.crystals_collected = 0
        player.stats.deaths += 1
        
        # Move to spawn point
        player.spawn(self.game_state.grid)
        
        # Clear validator state for fresh start
        self.validator.clear_player(player_id)
        
        # Send resync with new state
        await self._send_resync(player_id)
    
    async def _tick_loop(self) -> None:
        """Main game tick loop."""
        tick_interval = 1.0 / DEFAULT_TICK_CONFIG.tick_rate
        
        while self.running:
            try:
                if self.game_state:
                    # Debug heartbeat every 100 ticks
                    if self.game_state.current_tick % 100 == 0:
                        total_inputs = sum(len(buf) for buf in self.game_state.input_buffers.values())
                        print(f"💓 TICK {self.game_state.current_tick} | Players: {len(self.game_state.players)} | Queued Inputs: {total_inputs}", flush=True)
                    
                    # Process tick
                    tick_state = self.game_state.process_tick()
                    
                    # Feed movements to AI detector
                    t0 = time.time()
                    try:
                        # [FIX] Process ALL new moves since last check, not just current tick
                        # This ensures the AI detector sees every movement
                        for pid, player in self.game_state.players.items():
                            if player.stats.movement_history:
                                # Track how many moves we've already analyzed
                                if not hasattr(player.stats, '_ai_processed_count'):
                                    player.stats._ai_processed_count = 0
                                
                                # Convert deque to list for slicing (deque doesn't support slice notation)
                                history_list = list(player.stats.movement_history)
                                new_moves = history_list[player.stats._ai_processed_count:]
                                
                                for move in new_moves:
                                    await ai_detector.record_movement(pid, move, self.game_state.grid)
                                
                                # Update counter
                                player.stats._ai_processed_count = len(history_list)
                    except Exception as e:
                        print(f"⚠️ AI Detector Error: {e}")
                    
                    t1 = time.time()
                    if t1 - t0 > 0.05:
                         print(f"⚠️ SLOW AI LOOP: {(t1-t0)*1000:.1f}ms")
                    
                    # Send state updates to all clients
                    await self._broadcast_state(tick_state)
            except Exception as e:
                print(f"🔥 CRITICAL TICK LOOP ERROR: {e}")
                import traceback
                traceback.print_exc()
            
            # Wait for next tick
            await asyncio.sleep(tick_interval)
    
    async def _broadcast_state(self, tick_state) -> None:
        """Broadcast game state to all clients."""
        # [FIX] Iterate over a COPY (list) of keys
        for player_id in list(self.clients):
            # Get partial state for this player
            client_state = self.game_state.get_client_state(player_id)
            if client_state:
                await self._send_to_player(player_id, {
                    'type': 'STATE_UPDATE',
                    **client_state
                })
    
    async def _send_initial_state(self, player_id: str) -> None:
        """Send initial game state to new player."""
        if not self.game_state:
            return
        
        client_state = self.game_state.get_client_state(player_id)
        if client_state:
            await self._send_to_player(player_id, {
                'type': 'INITIAL_STATE',
                'tick_rate': DEFAULT_TICK_CONFIG.tick_rate,
                **client_state
            })
    
    async def _send_resync(self, player_id: str) -> None:
        """Send full resync to a player."""
        if not self.game_state:
            return
        
        resync = self.game_state.get_resync_state(player_id)
        if resync:
            await self._send_to_player(player_id, {
                'type': 'RESYNC',
                **resync
            })
    
    async def _send_to_player(self, player_id: str, data: dict) -> None:
        """Send message to specific player."""
        client = self.clients.get(player_id)
        if client:
            try:
                await client.websocket.send_json(data)
            except Exception:
                # Connection might be closed
                pass
    
    async def _broadcast(
        self,
        data: dict,
        exclude: Optional[Set[str]] = None
    ) -> None:
        """Broadcast message to all connected clients."""
        exclude = exclude or set()
        
        # [FIX] Iterate over a COPY of items
        for player_id, client in list(self.clients.items()):
            if player_id not in exclude:
                try:
                    await client.websocket.send_json(data)
                except Exception:
                    pass


# Global instance
game_ws = GameWebSocket()
