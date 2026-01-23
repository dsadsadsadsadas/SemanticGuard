#!/usr/bin/env python3
"""
🛡️ TREPAN System Tray (system_tray.py)
System tray icon for visibility and control

Features:
- Status indicator (Active/Paused/Alert)
- Right-click menu: Toggle Modes, Open Dashboard, View Logs
- Notification toasts for security events
- Hotkey registration for Secure Paste
"""

import os
import sys
import threading
import logging
from typing import Callable, Optional
from dataclasses import dataclass
from enum import Enum
import webbrowser

# Check for pystray availability
try:
    import pystray
    from pystray import MenuItem as Item
    from PIL import Image, ImageDraw, ImageFont
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("⚠️ System tray requires: pip install pystray pillow")


logger = logging.getLogger("TREPAN.Tray")


class TrepanStatus(Enum):
    ACTIVE = "active"      # Normal monitoring
    PAUSED = "paused"      # User paused monitoring
    ALERT = "alert"        # Security issue detected
    PROCESSING = "processing"  # Currently analyzing


@dataclass
class TrayConfig:
    """Configuration for the system tray."""
    on_toggle_pause: Optional[Callable[[], None]] = None
    on_open_logs: Optional[Callable[[], None]] = None
    on_open_dashboard: Optional[Callable[[], None]] = None
    on_quit: Optional[Callable[[], None]] = None
    on_secure_paste: Optional[Callable[[], None]] = None


class TrepanTray:
    """System tray icon for Trepan visibility and control."""
    
    # Color schemes for different states
    COLORS = {
        TrepanStatus.ACTIVE: ("#27ae60", "●"),      # Green
        TrepanStatus.PAUSED: ("#95a5a6", "○"),      # Gray
        TrepanStatus.ALERT: ("#e74c3c", "⚠"),       # Red
        TrepanStatus.PROCESSING: ("#3498db", "◐"),  # Blue
    }
    
    def __init__(self, config: TrayConfig):
        if not TRAY_AVAILABLE:
            raise RuntimeError("pystray and pillow are required for system tray")
        
        self.config = config
        self.status = TrepanStatus.ACTIVE
        self.is_paused = False
        self.icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None
        
    def _create_icon_image(self, status: TrepanStatus) -> Image.Image:
        """Create a dynamic icon based on current status."""
        color, symbol = self.COLORS[status]
        
        # Create 64x64 image with transparency
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Draw filled circle with status color
        padding = 4
        draw.ellipse(
            [padding, padding, size - padding, size - padding],
            fill=color,
            outline="#ffffff",
            width=2
        )
        
        # Draw shield outline
        shield_points = [
            (size // 2, 12),          # Top
            (size - 12, 20),          # Top right
            (size - 12, 40),          # Middle right
            (size // 2, size - 10),   # Bottom
            (12, 40),                 # Middle left
            (12, 20),                 # Top left
        ]
        draw.polygon(shield_points, outline="#ffffff", fill=None)
        
        # Draw "T" in center
        try:
            font = ImageFont.truetype("arial.ttf", 28)
        except:
            font = ImageFont.load_default()
        
        text = "T"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size - text_width) // 2
        y = (size - text_height) // 2 - 4
        draw.text((x, y), text, fill="#ffffff", font=font)
        
        return image
    
    def _build_menu(self) -> pystray.Menu:
        """Build the right-click context menu."""
        pause_text = "▶ Resume Monitoring" if self.is_paused else "⏸ Pause Monitoring"
        
        return pystray.Menu(
            Item(
                f"🛡️ Trepan ({self.status.value})",
                None,
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
            Item(
                "🔐 Secure Paste (Ctrl+Shift+V)",
                self._on_secure_paste,
                default=True
            ),
            pystray.Menu.SEPARATOR,
            Item(
                pause_text,
                self._on_toggle_pause
            ),
            Item(
                "📊 Open Dashboard",
                self._on_open_dashboard
            ),
            Item(
                "📜 View Logs",
                self._on_open_logs
            ),
            pystray.Menu.SEPARATOR,
            Item(
                "❌ Quit Trepan",
                self._on_quit
            )
        )
    
    def _on_toggle_pause(self, icon, item):
        """Toggle pause state."""
        self.is_paused = not self.is_paused
        self.set_status(TrepanStatus.PAUSED if self.is_paused else TrepanStatus.ACTIVE)
        
        if self.config.on_toggle_pause:
            self.config.on_toggle_pause()
        
        # Update menu
        self.icon.menu = self._build_menu()
    
    def _on_secure_paste(self, icon=None, item=None):
        """Trigger secure paste with policy dialog."""
        if self.config.on_secure_paste:
            self.config.on_secure_paste()
    
    def _on_open_dashboard(self, icon, item):
        """Open the Trepan dashboard (placeholder)."""
        if self.config.on_open_dashboard:
            self.config.on_open_dashboard()
        else:
            # Default: open GEMINI.md in default editor
            gemini_path = os.path.join(os.getcwd(), "GEMINI.md")
            if os.path.exists(gemini_path):
                os.startfile(gemini_path)
    
    def _on_open_logs(self, icon, item):
        """Open the log viewer."""
        if self.config.on_open_logs:
            self.config.on_open_logs()
        else:
            # Default: open ai_trace.txt
            trace_path = os.path.join(os.getcwd(), "ai_trace.txt")
            if os.path.exists(trace_path):
                os.startfile(trace_path)
    
    def _on_quit(self, icon, item):
        """Quit the application."""
        if self.config.on_quit:
            self.config.on_quit()
        icon.stop()
    
    def set_status(self, status: TrepanStatus):
        """Update the tray icon status."""
        self.status = status
        if self.icon:
            self.icon.icon = self._create_icon_image(status)
            self.icon.title = f"Trepan - {status.value.capitalize()}"
    
    def show_notification(self, title: str, message: str, 
                          status: TrepanStatus = TrepanStatus.ALERT):
        """Show a system notification toast."""
        if self.icon:
            # Temporarily change icon to alert state
            original_status = self.status
            self.set_status(status)
            
            try:
                self.icon.notify(message, title)
            except Exception as e:
                logger.warning(f"Notification failed: {e}")
            
            # Restore original status after a delay
            def restore():
                import time
                time.sleep(3)
                self.set_status(original_status)
            
            threading.Thread(target=restore, daemon=True).start()
    
    def start(self):
        """Start the system tray icon in a background thread."""
        def run():
            self.icon = pystray.Icon(
                name="trepan",
                icon=self._create_icon_image(self.status),
                title="Trepan - Active",
                menu=self._build_menu()
            )
            self.icon.run()
        
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        logger.info("🔔 System tray started")
    
    def stop(self):
        """Stop the system tray icon."""
        if self.icon:
            self.icon.stop()
        logger.info("🔕 System tray stopped")


def create_tray(
    on_toggle_pause: Optional[Callable] = None,
    on_secure_paste: Optional[Callable] = None,
    on_quit: Optional[Callable] = None
) -> Optional[TrepanTray]:
    """
    Convenience function to create and start the system tray.
    
    Returns None if tray is not available (missing dependencies).
    """
    if not TRAY_AVAILABLE:
        logger.warning("System tray not available - missing pystray/pillow")
        return None
    
    config = TrayConfig(
        on_toggle_pause=on_toggle_pause,
        on_secure_paste=on_secure_paste,
        on_quit=on_quit
    )
    
    tray = TrepanTray(config)
    tray.start()
    return tray


# --- DEMO ---
if __name__ == "__main__":
    import time
    
    print("Starting Trepan System Tray demo...")
    print("Look for the icon in your system tray!")
    
    def on_pause():
        print("⏸ Pause toggled!")
    
    def on_secure_paste():
        print("🔐 Secure paste triggered!")
    
    def on_quit():
        print("👋 Goodbye!")
        sys.exit(0)
    
    tray = create_tray(
        on_toggle_pause=on_pause,
        on_secure_paste=on_secure_paste,
        on_quit=on_quit
    )
    
    if tray:
        # Demo: cycle through statuses
        time.sleep(3)
        tray.show_notification("Security Alert", "Hardcoded secret detected in auth.py")
        
        time.sleep(5)
        tray.set_status(TrepanStatus.PROCESSING)
        
        time.sleep(3)
        tray.set_status(TrepanStatus.ACTIVE)
        
        # Keep running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            tray.stop()
    else:
        print("❌ Could not create system tray")
