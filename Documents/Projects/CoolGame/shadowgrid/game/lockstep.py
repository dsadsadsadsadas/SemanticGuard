"""
ShadowGrid Lockstep Protocol

Deterministic game-state synchronization with input validation.
"""

from __future__ import annotations
import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Deque, Tuple
from collections import deque
from enum import IntEnum, auto

from .constants import Direction, TickConfig, DEFAULT_TICK_CONFIG
from .world import Grid
from .player import Player


class InputType(IntEnum):
    """Types of player inputs."""
    MOVE = auto()
    INTERACT = auto()
    PING = auto()  # For latency measurement


@dataclass
class PlayerInput:
    """A validated player input for a specific tick."""
    player_id: str
    tick: int
    input_type: InputType
    direction: Direction = Direction.NONE
    timestamp: float = field(default_factory=time.time)
    client_hash: str = ""  # Client's state hash for verification


@dataclass
class TickState:
    """Complete game state at a specific tick."""
    tick: int
    grid_hash: str
    player_states: Dict[str, dict]
    timestamp: float = field(default_factory=time.time)
    
    def compute_hash(self) -> str:
        """Compute deterministic hash of this state."""
        data = f"{self.tick}:{self.grid_hash}:"
        for pid in sorted(self.player_states.keys()):
            ps = self.player_states[pid]
            data += f"{pid}:{ps['x']}:{ps['y']}:{ps['health']}:{ps['score']}:"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class ValidationResult:
    """Result of input validation."""
    valid: bool
    reason: str = ""
    severity: int = 0  # 0=ok, 1=warning, 2=suspicious, 3=cheat
    
    @staticmethod
    def ok() -> ValidationResult:
        return ValidationResult(valid=True)
    
    @staticmethod
    def warning(reason: str) -> ValidationResult:
        return ValidationResult(valid=True, reason=reason, severity=1)
    
    @staticmethod
    def suspicious(reason: str) -> ValidationResult:
        return ValidationResult(valid=False, reason=reason, severity=2)
    
    @staticmethod
    def cheat(reason: str) -> ValidationResult:
        return ValidationResult(valid=False, reason=reason, severity=3)


class GameState:
    """
    Authoritative game state manager.
    
    Implements deterministic lockstep protocol:
    1. Server maintains authoritative state
    2. Clients send inputs with their current tick
    3. Server validates inputs and advances state
    4. Server broadcasts state updates to all clients
    5. State hashes are compared for desync detection
    """
    
    def __init__(
        self,
        grid: Grid,
        config: TickConfig = DEFAULT_TICK_CONFIG
    ):
        self.grid = grid
        self.config = config
        
        self.current_tick: int = 0
        self.players: Dict[str, Player] = {}
        
        # Input buffer per player
        self.input_buffers: Dict[str, Deque[PlayerInput]] = {}
        
        # State history for rollback
        self.state_history: Deque[TickState] = deque(maxlen=60)
        
        # Validation tracking
        self.validation_log: List[Tuple[str, ValidationResult]] = []
        
        # Timing
        self.last_tick_time: float = time.time()
        self.tick_interval: float = 1.0 / config.tick_rate
    
    def add_player(self, player: Player) -> None:
        """Add a player to the game."""
        player.spawn(self.grid)
        self.players[player.player_id] = player
        self.input_buffers[player.player_id] = deque(maxlen=self.config.input_buffer_size)
    
    def remove_player(self, player_id: str) -> None:
        """Remove a player from the game."""
        self.players.pop(player_id, None)
        self.input_buffers.pop(player_id, None)
    
    def queue_input(self, input: PlayerInput) -> ValidationResult:
        """
        Queue a player input for processing.
        
        Validates:
        - Player exists
        - Input rate is reasonable
        """
        # Check player exists
        if input.player_id not in self.players:
            return ValidationResult.suspicious("Unknown player")
        
        # NOTE: Tick validation disabled for loose lockstep mode
        # Client sends timestamp in ms, server uses frame count
        # We just process all inputs as they come in
        
        # Check input rate (basic anti-spam)
        buffer = self.input_buffers.get(input.player_id, deque())
        if len(buffer) >= self.config.input_buffer_size:
            # Check timing of oldest input
            oldest = buffer[0]
            time_span = input.timestamp - oldest.timestamp
            if time_span < 0.1 and len(buffer) > 3:
                return ValidationResult.suspicious(
                    "Input rate too high"
                )
        
        # Queue the input
        self.input_buffers[input.player_id].append(input)
        return ValidationResult.ok()
    
    def process_tick(self) -> TickState:
        """
        Process one game tick.
        
        1. Collect inputs from all buffers
        2. Validate and apply inputs deterministically
        3. Update game state
        4. Generate and store tick state
        """
        # Process inputs in deterministic order
        for player_id in sorted(self.input_buffers.keys()):
            buffer = self.input_buffers[player_id]
            
            # Process ALL buffered inputs (loose lockstep - no strict tick matching)
            while buffer:
                input_item = buffer.popleft()
                player = self.players.get(player_id)
                old_pos = (player.x, player.y) if player else None
                
                result = self._apply_input(input_item)
                
                # Debug: Log movement after apply
                if player and self.current_tick % 100 == 0:
                    new_pos = (player.x, player.y)
                    print(f"🎮 Move {player_id}: {old_pos} -> {new_pos} | Dir: {input_item.direction}", flush=True)
                
                if result.severity > 0:
                    self.validation_log.append((player_id, result))
        
        # Generate tick state
        tick_state = TickState(
            tick=self.current_tick,
            grid_hash=self.grid.compute_hash(),
            player_states={
                pid: player.get_state()
                for pid, player in self.players.items()
            }
        )
        
        self.state_history.append(tick_state)
        self.current_tick += 1
        self.last_tick_time = time.time()
        
        return tick_state
    
    def _apply_input(self, input: PlayerInput) -> ValidationResult:
        """Apply a validated input to game state."""
        player = self.players.get(input.player_id)
        if not player:
            return ValidationResult.suspicious("Player not found")
        
        if not player.alive:
            return ValidationResult.warning("Input from dead player")
        
        if input.input_type == InputType.MOVE:
            success, message = player.move(
                input.direction,
                self.grid,
                self.current_tick,
                timestamp=input.timestamp
            )
            
            if not success:
                # Check for impossible move attempts
                if "wall" in message.lower() or "bounds" in message.lower():
                    # Could be lag or could be cheat attempt
                    # We'll track but not immediately flag
                    return ValidationResult.warning(f"Invalid move: {message}")
            
            return ValidationResult.ok()
        
        elif input.input_type == InputType.PING:
            return ValidationResult.ok()
        
        return ValidationResult.warning(f"Unknown input type: {input.input_type}")
    
    def validate_client_state(
        self,
        player_id: str,
        client_tick: int,
        client_hash: str
    ) -> ValidationResult:
        """
        Validate client's state hash against server history.
        
        Used to detect state manipulation.
        """
        # Find matching tick in history
        for state in self.state_history:
            if state.tick == client_tick:
                server_hash = state.compute_hash()
                if client_hash != server_hash:
                    return ValidationResult.cheat(
                        f"State mismatch at tick {client_tick}: "
                        f"client={client_hash}, server={server_hash}"
                    )
                return ValidationResult.ok()
        
        # Tick not in history (too old)
        return ValidationResult.warning(
            f"Tick {client_tick} not in state history"
        )
    
    def get_resync_state(self, player_id: str) -> Optional[dict]:
        """Get state for client resynchronization."""
        if not self.state_history:
            return None
        
        latest = self.state_history[-1]
        
        return {
            'tick': latest.tick,
            'grid_hash': latest.grid_hash,
            'grid_state': self.grid.get_full_state(),  # Only for server
            'player_state': latest.player_states.get(player_id),
            'all_players': {
                pid: {
                    'x': ps['x'],
                    'y': ps['y'],
                    'alive': ps['alive']
                }
                for pid, ps in latest.player_states.items()
            }
        }
    
    def get_client_state(self, player_id: str) -> Optional[dict]:
        """Get state for a specific client (partial observability)."""
        player = self.players.get(player_id)
        if not player:
            return None
        
        return {
            'tick': self.current_tick,
            'player': player.get_state(),
            'visible_grid': self.grid.get_visible_state(
                player.x, player.y,
                player.config.visibility_radius
            ),
            'crystals_remaining': self.grid.crystals_remaining,
            'other_players': [
                {'x': p.x, 'y': p.y, 'alive': p.alive}
                for pid, p in self.players.items()
                if pid != player_id and abs(p.x - player.x) <= 1 and abs(p.y - player.y) <= 1
            ]
        }
    
    def get_suspicious_players(self, min_severity: int = 2) -> List[str]:
        """Get list of players with suspicious validation results."""
        suspicious = {}
        for player_id, result in self.validation_log:
            if result.severity >= min_severity:
                if player_id not in suspicious:
                    suspicious[player_id] = []
                suspicious[player_id].append(result)
        return list(suspicious.keys())


class LockstepProtocol:
    """
    Network protocol handler for lockstep synchronization.
    
    Message types:
    - INPUT: Player input from client
    - STATE: Full state update from server
    - SYNC: Resync request/response
    - HASH: State hash for verification
    """
    
    @staticmethod
    def encode_input(input: PlayerInput) -> dict:
        """Encode player input for network transmission."""
        return {
            'type': 'INPUT',
            'player_id': input.player_id,
            'tick': input.tick,
            'input_type': int(input.input_type),
            'direction': int(input.direction),
            'timestamp': input.timestamp,
            'client_hash': input.client_hash
        }
    
    @staticmethod
    def decode_input(data: dict) -> PlayerInput:
        """Decode player input from network data."""
        # Handle input_type - default to MOVE if not provided
        input_type_raw = data.get('input_type', 1)  # 1 = MOVE
        if isinstance(input_type_raw, int):
            input_type = InputType(input_type_raw)
        else:
            input_type = InputType.MOVE
        
        # Handle direction - can be string ("UP") or int (1)
        direction_raw = data.get('direction', 0)
        if isinstance(direction_raw, str):
            direction_map = {'UP': 1, 'DOWN': 2, 'LEFT': 3, 'RIGHT': 4, 'NONE': 0}
            direction = Direction(direction_map.get(direction_raw.upper(), 0))
        elif isinstance(direction_raw, int):
            direction = Direction(direction_raw)
        else:
            direction = Direction.NONE
        
        return PlayerInput(
            player_id=data['player_id'],
            tick=data.get('tick', 0),
            input_type=input_type,
            direction=direction,
            timestamp=data.get('timestamp', time.time()),
            client_hash=data.get('client_hash', '')
        )
    
    @staticmethod
    def encode_state(state: TickState) -> dict:
        """Encode tick state for network transmission."""
        return {
            'type': 'STATE',
            'tick': state.tick,
            'grid_hash': state.grid_hash,
            'players': state.player_states,
            'state_hash': state.compute_hash()
        }
    
    @staticmethod
    def encode_sync_request(player_id: str, tick: int) -> dict:
        """Encode resync request from client."""
        return {
            'type': 'SYNC_REQUEST',
            'player_id': player_id,
            'last_tick': tick
        }
    
    @staticmethod
    def encode_sync_response(resync_data: dict) -> dict:
        """Encode resync response from server."""
        return {
            'type': 'SYNC_RESPONSE',
            **resync_data
        }
