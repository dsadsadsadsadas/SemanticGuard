"""
ShadowGrid Game Client

Pygame-based client with fog-of-war rendering and WebSocket communication.
"""

from __future__ import annotations
import asyncio
import json
import time
import uuid
import math
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from queue import Queue

import pygame
import websockets

from ..game.constants import (
    TileType, Direction, DIRECTION_VECTORS,
    TILE_COLORS, PLAYER_COLOR, FOG_COLOR,
    TILE_SIZE, UI_BACKGROUND, UI_TEXT, UI_ACCENT,
    DEFAULT_PLAYER_CONFIG
)


@dataclass
class ClientState:
    """Local client state."""
    player_id: str
    x: int = 0
    y: int = 0
    health: int = 100
    score: int = 0
    alive: bool = True
    tick: int = 0
    
    # Visible grid (POMDP observation)
    visible_grid: List[List[int]] = field(default_factory=list)
    
    # Other visible players
    other_players: List[dict] = field(default_factory=list)
    
    # Game info
    crystals_remaining: int = 0
    tick_rate: int = 20
    
    # Messages
    last_message: str = ""
    message_time: float = 0.0
    
    # Detection dashboard data
    detection_score: float = 0.0
    tier1_score: float = 0.0
    tier2_score: float = 0.0
    suspicion_reasons: List[str] = field(default_factory=list)
    feature_values: Dict[str, float] = field(default_factory=dict)


class NetworkThread(threading.Thread):
    """Background thread for WebSocket communication."""
    
    def __init__(
        self,
        server_url: str,
        player_id: str,
        send_queue: Queue,
        receive_queue: Queue
    ):
        super().__init__(daemon=True)
        self.server_url = server_url
        self.player_id = player_id
        self.send_queue = send_queue
        self.receive_queue = receive_queue
        self.running = True
        self.connected = False
    
    def run(self):
        """Run the async event loop in thread."""
        asyncio.run(self._run_async())
    
    async def _run_async(self):
        """Async connection handler."""
        url = f"{self.server_url}/ws/{self.player_id}"
        
        try:
            async with websockets.connect(url) as ws:
                self.connected = True
                
                # Receive and send concurrently
                await asyncio.gather(
                    self._receive_loop(ws),
                    self._send_loop(ws)
                )
        
        except Exception as e:
            self.receive_queue.put({
                'type': 'CONNECTION_ERROR',
                'error': str(e)
            })
        
        finally:
            self.connected = False
    
    async def _receive_loop(self, ws):
        """Receive messages from server."""
        while self.running:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=0.1)
                data = json.loads(message)
                self.receive_queue.put(data)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
    
    async def _send_loop(self, ws):
        """Send messages to server."""
        while self.running:
            try:
                # Non-blocking check for messages
                if not self.send_queue.empty():
                    data = self.send_queue.get_nowait()
                    await ws.send(json.dumps(data))
                else:
                    await asyncio.sleep(0.01)
            except Exception:
                break
    
    def stop(self):
        """Stop the network thread."""
        self.running = False


class ShadowGridClient:
    """
    Main game client with pygame rendering.
    
    Features:
    - Fog-of-war visualization
    - Smooth movement
    - Real-time server sync
    - Input buffering for latency compensation
    """
    
    WINDOW_WIDTH = 800
    WINDOW_HEIGHT = 640
    UI_HEIGHT = 80
    
    def __init__(self, server_url: str = "ws://localhost:8000"):
        self.server_url = server_url
        self.player_id = f"player_{uuid.uuid4().hex[:8]}"
        
        # State
        self.state = ClientState(player_id=self.player_id)
        
        # Networking
        self.send_queue: Queue = Queue()
        self.receive_queue: Queue = Queue()
        self.network_thread: Optional[NetworkThread] = None
        
        # Pygame
        self.screen: Optional[pygame.Surface] = None
        self.clock: Optional[pygame.time.Clock] = None
        self.font: Optional[pygame.font.Font] = None
        self.small_font: Optional[pygame.font.Font] = None
        
        # Input
        self.last_input_time: float = 0.0
        self.input_cooldown: float = 0.05  # 50ms between inputs
        
        # Animation
        self.visual_x: float = 0.0
        self.visual_y: float = 0.0
        self.animation_speed: float = 10.0
        
        # Game over state
        self.game_over: bool = False
        self.death_time: float = 0.0
        
        # Detection dashboard
        self.show_dashboard: bool = True  # Toggle with D key
        self.dashboard_width: int = 220
        
        # Cheat mode (for testing detection)
        self.cheat_mode: bool = False
        self.cheat_speed_multiplier: float = 1.0
        
        # Movement tracking for local detection simulation
        self.move_history: List[dict] = []
        self.last_move_time: float = 0.0
        self.total_moves: int = 0
        self.fog_violations: int = 0
        self.speed_violations: int = 0
        
        self.running = False
    
    def connect(self) -> bool:
        """Connect to game server."""
        self.network_thread = NetworkThread(
            self.server_url,
            self.player_id,
            self.send_queue,
            self.receive_queue
        )
        self.network_thread.start()
        
        # Wait for connection
        start = time.time()
        while time.time() - start < 5.0:
            if self.network_thread.connected:
                return True
            if not self.receive_queue.empty():
                msg = self.receive_queue.get()
                if msg.get('type') == 'CONNECTION_ERROR':
                    print(f"Connection failed: {msg.get('error')}")
                    return False
            time.sleep(0.1)
        
        return False
    
    def disconnect(self):
        """Disconnect from server."""
        if self.network_thread:
            self.network_thread.stop()
            self.network_thread.join(timeout=1.0)
    
    def init_pygame(self):
        """Initialize pygame systems."""
        pygame.init()
        pygame.display.set_caption(f"ShadowGrid - {self.player_id}")
        
        self.screen = pygame.display.set_mode(
            (self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        )
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)
    
    def run(self):
        """Main game loop."""
        self.init_pygame()
        
        if not self.connect():
            print("Failed to connect to server")
            pygame.quit()
            return
        
        self.running = True
        
        try:
            while self.running:
                dt = self.clock.tick(60) / 1000.0  # Delta time in seconds
                
                # Process events
                self._handle_events()
                
                # Process network messages
                self._process_messages()
                
                # Update animation
                self._update_animation(dt)
                
                # Render
                self._render()
                
                pygame.display.flip()
        
        finally:
            self.disconnect()
            pygame.quit()
    
    def _handle_events(self):
        """Handle pygame events and input."""
        current_time = time.time()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                    return
                
                # Restart on R key when dead
                if event.key == pygame.K_r and self.game_over:
                    self._request_restart()
                    return
                
                # Toggle dashboard with D key
                if event.key == pygame.K_d and not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    self.show_dashboard = not self.show_dashboard
                    self._show_message(f"Dashboard {'ON' if self.show_dashboard else 'OFF'}")
                
                # Toggle cheat mode with C key
                if event.key == pygame.K_c:
                    self.cheat_mode = not self.cheat_mode
                    if self.cheat_mode:
                        self.cheat_speed_multiplier = 2.0  # Move faster
                        self._show_message("⚠️ CHEAT MODE ON - Speed boost enabled")
                    else:
                        self.cheat_speed_multiplier = 1.0
                        self._show_message("Cheat mode OFF")
        
        # Continuous movement with cooldown
        if current_time - self.last_input_time < self.input_cooldown:
            return
        
        keys = pygame.key.get_pressed()
        direction = None
        
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            direction = Direction.UP
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            direction = Direction.DOWN
        elif keys[pygame.K_LEFT] or keys[pygame.K_a]:
            direction = Direction.LEFT
        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            direction = Direction.RIGHT
        
        if direction is not None and not self.game_over:
            self._send_input(direction)
            self.last_input_time = current_time
    
    def _request_restart(self):
        """Request game restart from server."""
        self.send_queue.put({
            'type': 'RESTART',
            'player_id': self.state.player_id
        })
        
        # Reset local state
        self.game_over = False
        self.state.alive = True
        self.state.health = 100
        self.state.score = 0
        self._show_message("Restarting...")
    
    def _send_input(self, direction: Direction):
        """Send movement input to server."""
        current_time = time.time()
        
        # Track movement for detection
        self.move_history.append({
            'direction': direction,
            'time': current_time,
            'interval': current_time - self.last_move_time if self.last_move_time > 0 else 0,
            'cheat_mode': self.cheat_mode
        })
        self.last_move_time = current_time
        self.total_moves += 1
        
        # Keep history bounded
        if len(self.move_history) > 100:
            self.move_history = self.move_history[-100:]
        
        # Update detection score locally
        self._update_detection_score()
        
        # In cheat mode, send multiple inputs for speed boost
        num_inputs = 2 if self.cheat_mode else 1
        
        for _ in range(num_inputs):
            self.send_queue.put({
                'type': 'INPUT',
                'tick': self.state.tick,
                'input_type': 1,  # MOVE
                'direction': int(direction),
                'timestamp': current_time,
                'cheat_mode': self.cheat_mode  # Server can detect this flag
            })
            
            if self.cheat_mode:
                self.speed_violations += 1
    
    def _update_detection_score(self):
        """Update local detection score based on behavior."""
        score = 0.0
        reasons = []
        
        # Speed violations
        if self.speed_violations > 0:
            speed_score = min(0.5, self.speed_violations * 0.05)
            score += speed_score
            if self.speed_violations > 3:
                reasons.append(f"Speed violations: {self.speed_violations}")
        
        # Input timing analysis
        if len(self.move_history) >= 5:
            intervals = [m['interval'] for m in self.move_history[-20:] if m['interval'] > 0]
            if intervals:
                avg_interval = sum(intervals) / len(intervals)
                std_interval = (sum((i - avg_interval)**2 for i in intervals) / len(intervals)) ** 0.5
                
                # Too regular = suspicious (bot-like)
                if std_interval < 0.01 and avg_interval < 0.1:
                    score += 0.2
                    reasons.append("Input timing too regular")
                
                # Too fast = suspicious
                if avg_interval < 0.03:
                    score += 0.2
                    reasons.append("Inhuman input speed")
        
        # Cheat mode flag
        if self.cheat_mode:
            score += 0.3
            reasons.append("Cheat mode active")
        
        # Store feature values for dashboard
        self.state.feature_values = {
            'speed_violations': self.speed_violations,
            'total_moves': self.total_moves,
            'fog_violations': self.fog_violations,
            'cheat_mode': 1 if self.cheat_mode else 0
        }
        
        self.state.detection_score = min(1.0, score)
        self.state.tier1_score = score * 0.8
        self.state.suspicion_reasons = reasons
    
    def _process_messages(self):
        """Process incoming server messages."""
        while not self.receive_queue.empty():
            msg = self.receive_queue.get()
            msg_type = msg.get('type')
            
            if msg_type == 'INITIAL_STATE':
                self._handle_initial_state(msg)
            elif msg_type == 'STATE_UPDATE':
                self._handle_state_update(msg)
            elif msg_type == 'RESYNC':
                self._handle_resync(msg)
            elif msg_type == 'INPUT_REJECTED':
                self._show_message(f"Move rejected: {msg.get('reason', 'unknown')}")
            elif msg_type == 'PLAYER_JOINED':
                self._show_message(f"Player joined! ({msg.get('player_count')} online)")
            elif msg_type == 'PLAYER_LEFT':
                self._show_message(f"Player left. ({msg.get('player_count')} online)")
    
    def _handle_initial_state(self, msg: dict):
        """Handle initial state from server."""
        self.state.tick_rate = msg.get('tick_rate', 20)
        self._apply_state(msg)
        
        # Initialize visual position
        self.visual_x = float(self.state.x)
        self.visual_y = float(self.state.y)
        
        self._show_message("Connected to ShadowGrid!")
    
    def _handle_state_update(self, msg: dict):
        """Handle state update from server."""
        self._apply_state(msg)
    
    def _handle_resync(self, msg: dict):
        """Handle full resync from server."""
        self._apply_state(msg)
        self.visual_x = float(self.state.x)
        self.visual_y = float(self.state.y)
        self._show_message("Resynchronized with server")
    
    def _apply_state(self, msg: dict):
        """Apply server state to local state."""
        player = msg.get('player', {})
        
        self.state.x = player.get('x', self.state.x)
        self.state.y = player.get('y', self.state.y)
        self.state.health = player.get('health', self.state.health)
        self.state.score = player.get('score', self.state.score)
        self.state.alive = player.get('alive', self.state.alive)
        self.state.tick = msg.get('tick', self.state.tick)
        
        self.state.visible_grid = msg.get('visible_grid', self.state.visible_grid)
        self.state.other_players = msg.get('other_players', [])
        self.state.crystals_remaining = msg.get('crystals_remaining', 0)
        
        # Check for death
        if not self.state.alive and not self.game_over:
            self.game_over = True
            self.death_time = time.time()
            self._show_message("You died! Press R to restart")
    
    def _update_animation(self, dt: float):
        """Update smooth movement animation."""
        target_x = float(self.state.x)
        target_y = float(self.state.y)
        
        # Lerp toward target
        self.visual_x += (target_x - self.visual_x) * self.animation_speed * dt
        self.visual_y += (target_y - self.visual_y) * self.animation_speed * dt
        
        # Snap if close enough
        if abs(target_x - self.visual_x) < 0.01:
            self.visual_x = target_x
        if abs(target_y - self.visual_y) < 0.01:
            self.visual_y = target_y
    
    def _show_message(self, text: str):
        """Display a temporary message."""
        self.state.last_message = text
        self.state.message_time = time.time()
    
    def _render(self):
        """Render the game."""
        self.screen.fill(UI_BACKGROUND)
        
        # Calculate grid offset to center player
        grid_offset_x = self.WINDOW_WIDTH // 2 - int(self.visual_x * TILE_SIZE)
        grid_offset_y = (self.WINDOW_HEIGHT - self.UI_HEIGHT) // 2 - int(self.visual_y * TILE_SIZE)
        
        # Render grid
        self._render_grid(grid_offset_x, grid_offset_y)
        
        # Render other players
        self._render_other_players(grid_offset_x, grid_offset_y)
        
        # Render player
        self._render_player()
        
        # Render UI
        self._render_ui()
        
        # Render detection dashboard
        if self.show_dashboard:
            self._render_dashboard()
        
        # Render death screen overlay
        if self.game_over:
            self._render_death_screen()
    
    def _render_grid(self, offset_x: int, offset_y: int):
        """Render the visible grid with fog."""
        if not self.state.visible_grid:
            return
        
        for y, row in enumerate(self.state.visible_grid):
            for x, tile_type in enumerate(row):
                screen_x = offset_x + x * TILE_SIZE
                screen_y = offset_y + y * TILE_SIZE
                
                # Skip if off-screen
                if (screen_x < -TILE_SIZE or screen_x > self.WINDOW_WIDTH or
                    screen_y < -TILE_SIZE or screen_y > self.WINDOW_HEIGHT - self.UI_HEIGHT):
                    continue
                
                rect = pygame.Rect(screen_x, screen_y, TILE_SIZE - 1, TILE_SIZE - 1)
                
                if tile_type == -1:
                    # Fog
                    pygame.draw.rect(self.screen, FOG_COLOR, rect)
                else:
                    # Known tile
                    color = TILE_COLORS.get(TileType(tile_type), TILE_COLORS[TileType.EMPTY])
                    pygame.draw.rect(self.screen, color, rect)
                    
                    # Add visual effects for special tiles
                    if tile_type == TileType.CRYSTAL:
                        # Sparkle effect
                        center = rect.center
                        pygame.draw.circle(self.screen, (255, 255, 255), center, 4)
                    elif tile_type == TileType.LAVA:
                        # Glow effect
                        pygame.draw.rect(self.screen, (255, 120, 80), rect.inflate(-4, -4))
    
    def _render_other_players(self, offset_x: int, offset_y: int):
        """Render other visible players."""
        for other in self.state.other_players:
            if not other.get('alive', True):
                continue
            
            ox = other.get('x', 0)
            oy = other.get('y', 0)
            
            screen_x = offset_x + ox * TILE_SIZE + TILE_SIZE // 2
            screen_y = offset_y + oy * TILE_SIZE + TILE_SIZE // 2
            
            # Draw as different color
            pygame.draw.circle(
                self.screen,
                (255, 200, 100),  # Orange for others
                (screen_x, screen_y),
                TILE_SIZE // 3
            )
    
    def _render_player(self):
        """Render the player at screen center."""
        center_x = self.WINDOW_WIDTH // 2
        center_y = (self.WINDOW_HEIGHT - self.UI_HEIGHT) // 2
        
        # Player glow
        pygame.draw.circle(
            self.screen,
            (97, 218, 251, 50),
            (center_x, center_y),
            TILE_SIZE // 2 + 4
        )
        
        # Player body
        pygame.draw.circle(
            self.screen,
            PLAYER_COLOR,
            (center_x, center_y),
            TILE_SIZE // 3
        )
        
        # Health indicator ring
        if self.state.health < 100:
            health_angle = (self.state.health / 100) * 360
            # Draw partial arc for health
            pygame.draw.arc(
                self.screen,
                (255, 100, 100) if self.state.health < 50 else (100, 255, 100),
                pygame.Rect(center_x - 15, center_y - 15, 30, 30),
                0,
                health_angle * 3.14159 / 180,
                3
            )
    
    def _render_ui(self):
        """Render the UI panel."""
        ui_rect = pygame.Rect(0, self.WINDOW_HEIGHT - self.UI_HEIGHT, self.WINDOW_WIDTH, self.UI_HEIGHT)
        pygame.draw.rect(self.screen, (25, 28, 35), ui_rect)
        pygame.draw.line(
            self.screen,
            UI_ACCENT,
            (0, self.WINDOW_HEIGHT - self.UI_HEIGHT),
            (self.WINDOW_WIDTH, self.WINDOW_HEIGHT - self.UI_HEIGHT),
            2
        )
        
        # Stats
        y_offset = self.WINDOW_HEIGHT - self.UI_HEIGHT + 10
        
        # Health
        health_text = self.font.render(f"HP: {self.state.health}", True, 
            (255, 100, 100) if self.state.health < 50 else UI_TEXT)
        self.screen.blit(health_text, (20, y_offset))
        
        # Score
        score_text = self.font.render(f"Score: {self.state.score}", True, UI_ACCENT)
        self.screen.blit(score_text, (150, y_offset))
        
        # Crystals
        crystal_text = self.font.render(f"Crystals: {self.state.crystals_remaining}", True, 
            TILE_COLORS[TileType.CRYSTAL])
        self.screen.blit(crystal_text, (320, y_offset))
        
        # Position
        pos_text = self.small_font.render(f"({self.state.x}, {self.state.y})", True, (100, 100, 100))
        self.screen.blit(pos_text, (500, y_offset + 5))
        
        # Tick
        tick_text = self.small_font.render(f"Tick: {self.state.tick}", True, (100, 100, 100))
        self.screen.blit(tick_text, (600, y_offset + 5))
        
        # Connection status
        connected = self.network_thread and self.network_thread.connected
        status_color = (100, 255, 100) if connected else (255, 100, 100)
        status_text = self.small_font.render("●" if connected else "○", True, status_color)
        self.screen.blit(status_text, (self.WINDOW_WIDTH - 30, y_offset + 5))
        
        # Message (with fade)
        if self.state.last_message:
            age = time.time() - self.state.message_time
            if age < 3.0:
                alpha = int(255 * (1 - age / 3.0))
                msg_surface = self.small_font.render(self.state.last_message, True, UI_TEXT)
                msg_surface.set_alpha(alpha)
                self.screen.blit(msg_surface, (20, y_offset + 40))
    
    def _render_dashboard(self):
        """Render the detection dashboard panel."""
        panel_x = self.WINDOW_WIDTH - self.dashboard_width - 10
        panel_y = 10
        panel_height = 320
        
        # Panel background
        panel_rect = pygame.Rect(panel_x, panel_y, self.dashboard_width, panel_height)
        panel_surface = pygame.Surface((self.dashboard_width, panel_height))
        panel_surface.set_alpha(220)
        panel_surface.fill((20, 25, 35))
        self.screen.blit(panel_surface, (panel_x, panel_y))
        
        # Border
        border_color = (255, 80, 80) if self.state.detection_score > 0.5 else (80, 200, 120)
        pygame.draw.rect(self.screen, border_color, panel_rect, 2)
        
        # Title
        title_color = (255, 100, 100) if self.cheat_mode else UI_ACCENT
        title = "⚠️ DETECTION AI" if self.cheat_mode else "🛡️ DETECTION AI"
        title_text = self.small_font.render(title, True, title_color)
        self.screen.blit(title_text, (panel_x + 10, panel_y + 8))
        
        # Toggle hint
        hint = self.small_font.render("D: hide | C: cheat", True, (100, 100, 100))
        self.screen.blit(hint, (panel_x + 10, panel_y + 28))
        
        y = panel_y + 55
        
        # Detection score bar
        self._render_score_bar(
            panel_x + 10, y, 
            self.dashboard_width - 20, 20,
            self.state.detection_score,
            "Detection Score",
            (255, 80, 80) if self.state.detection_score > 0.5 else (80, 200, 120)
        )
        y += 35
        
        # Tier 1 score bar
        self._render_score_bar(
            panel_x + 10, y,
            self.dashboard_width - 20, 14,
            self.state.tier1_score,
            "Tier 1 (XGBoost)",
            (255, 180, 80)
        )
        y += 25
        
        # Feature values
        y += 5
        features_title = self.small_font.render("Features:", True, UI_TEXT)
        self.screen.blit(features_title, (panel_x + 10, y))
        y += 18
        
        for key, value in self.state.feature_values.items():
            if isinstance(value, float):
                text = f"  {key}: {value:.2f}"
            else:
                text = f"  {key}: {value}"
            
            color = (255, 150, 150) if value > 0 and key in ['speed_violations', 'fog_violations', 'cheat_mode'] else (150, 150, 150)
            feat_text = self.small_font.render(text[:25], True, color)
            self.screen.blit(feat_text, (panel_x + 10, y))
            y += 16
        
        # Suspicion reasons
        y += 5
        if self.state.suspicion_reasons:
            reasons_title = self.small_font.render("Reasons:", True, (255, 100, 100))
            self.screen.blit(reasons_title, (panel_x + 10, y))
            y += 18
            
            for reason in self.state.suspicion_reasons[:4]:
                reason_text = self.small_font.render(f"• {reason[:22]}", True, (255, 150, 150))
                self.screen.blit(reason_text, (panel_x + 10, y))
                y += 16
        else:
            ok_text = self.small_font.render("✓ No issues detected", True, (100, 200, 100))
            self.screen.blit(ok_text, (panel_x + 10, y))
        
        # Cheat mode indicator
        if self.cheat_mode:
            y = panel_y + panel_height - 25
            cheat_text = self.font.render("⚡ CHEATING", True, (255, 50, 50))
            cheat_rect = cheat_text.get_rect(center=(panel_x + self.dashboard_width // 2, y))
            self.screen.blit(cheat_text, cheat_rect)
    
    def _render_score_bar(
        self, x: int, y: int, width: int, height: int,
        value: float, label: str, color: tuple
    ):
        """Render a score bar with label."""
        # Label
        label_text = self.small_font.render(f"{label}: {value:.0%}", True, UI_TEXT)
        self.screen.blit(label_text, (x, y - 14))
        
        # Background bar
        bg_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (40, 45, 55), bg_rect)
        
        # Fill bar
        fill_width = int(width * min(1.0, value))
        if fill_width > 0:
            fill_rect = pygame.Rect(x, y, fill_width, height)
            pygame.draw.rect(self.screen, color, fill_rect)
        
        # Border
        pygame.draw.rect(self.screen, (60, 65, 75), bg_rect, 1)
    
    def _render_death_screen(self):
        """Render death overlay screen."""
        # Semi-transparent red overlay
        overlay = pygame.Surface((self.WINDOW_WIDTH, self.WINDOW_HEIGHT - self.UI_HEIGHT))
        overlay.set_alpha(180)
        overlay.fill((40, 10, 10))
        self.screen.blit(overlay, (0, 0))
        
        # Death message
        death_text = self.font.render("YOU DIED", True, (255, 80, 80))
        text_rect = death_text.get_rect(center=(self.WINDOW_WIDTH // 2, 200))
        self.screen.blit(death_text, text_rect)
        
        # Score display
        score_text = self.font.render(f"Final Score: {self.state.score}", True, UI_ACCENT)
        score_rect = score_text.get_rect(center=(self.WINDOW_WIDTH // 2, 260))
        self.screen.blit(score_text, score_rect)
        
        # Restart prompt (pulsing)
        pulse = abs((time.time() * 2) % 2 - 1)  # 0-1-0 pulsing
        alpha = int(150 + 105 * pulse)
        
        restart_text = self.font.render("Press R to Restart", True, (255, 255, 255))
        restart_text.set_alpha(alpha)
        restart_rect = restart_text.get_rect(center=(self.WINDOW_WIDTH // 2, 340))
        self.screen.blit(restart_text, restart_rect)
        
        # Controls hint
        hint_text = self.small_font.render("ESC to quit", True, (150, 150, 150))
        hint_rect = hint_text.get_rect(center=(self.WINDOW_WIDTH // 2, 400))
        self.screen.blit(hint_text, hint_rect)


def main():
    """Entry point for client."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ShadowGrid Client")
    parser.add_argument("--server", default="ws://localhost:8000", help="Server URL")
    args = parser.parse_args()
    
    client = ShadowGridClient(server_url=args.server)
    client.run()


if __name__ == "__main__":
    main()
