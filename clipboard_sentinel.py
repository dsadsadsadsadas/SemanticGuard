#!/usr/bin/env python3
"""
🛡️ TREPAN Clipboard Sentinel (TR-03 + TR-05 + TR-06 + TR-07 + TR-08)
Semantic Firewall: Wires the Drift Engine into clipboard monitoring.

TR-05: Thread-safe UI launching via Queue.
TR-06: Cooldown timer + Image detection skip.
TR-07: Shrinkage Detector (Paranoia Mode).
TR-08: Hardened Safety Heuristics (Hard Block on critical patterns).
"""

import threading
import time
import logging

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False
    pyperclip = None

try:
    from drift_engine import drift_monitor
    HAS_DRIFT = drift_monitor.is_ready
except ImportError:
    HAS_DRIFT = False
    drift_monitor = None

# TR-08: Import hardened safety heuristics
try:
    from safety_heuristics import safety_guard
    HAS_SAFETY = True
except ImportError:
    HAS_SAFETY = False
    safety_guard = None


class ClipboardSentinel:
    """
    Monitors clipboard for semantic drift and critical security patterns.
    Uses a Queue to signal the main thread for UI operations.
    """
    
    def __init__(self, check_interval: float = 1.0, drift_threshold: float = 0.4):
        self.logger = logging.getLogger("Trepan.Sentinel")
        self.interval = check_interval
        self.base_threshold = drift_threshold
        self.last_content = ""
        self.is_active = True
        self.ui_queue = None
        self.last_trigger_time = 0

    def set_queue(self, q):
        """Link the sentinel to the main thread's UI request queue."""
        self.ui_queue = q

    def start_daemon(self):
        """Start the monitoring loop in a background daemon thread."""
        self.logger.info("[*] Starting Clipboard Sentinel (Daemon Mode)")
        t = threading.Thread(target=self.scan_loop, daemon=True)
        t.start()

    def get_clipboard(self) -> str:
        """Safely get clipboard content."""
        if not HAS_PYPERCLIP or not pyperclip:
            return ""
        try:
            return pyperclip.paste()
        except Exception:
            return ""

    def _is_image_content(self, content: str) -> bool:
        """TR-06: Detect if clipboard contains image/binary content."""
        if not content:
            return False
        if not isinstance(content, str):
            return True
        if '\x00' in content:
            return True
        return False

    def scan_loop(self):
        """Main monitoring loop running in background."""
        self.logger.info("[*] Clipboard Sentinel: WATCHING")
        
        # Initialize with current clipboard content
        self.last_content = self.get_clipboard()
        
        while self.is_active:
            try:
                current_content = self.get_clipboard()
                
                # Check 0: TR-06 - Skip images/binary
                if self._is_image_content(current_content):
                    time.sleep(self.interval)
                    continue
                
                # Check 1: Is content different and non-empty?
                if current_content != self.last_content and current_content.strip():
                    
                    # Check 2: TR-06 - Cooldown period
                    if (time.time() - self.last_trigger_time) < 1.5:
                        time.sleep(0.5)
                        continue
                    
                    # Only analyze if we have previous content
                    if self.last_content:
                        
                        # ============================================
                        # TR-08: HARD BLOCK CHECK (HIGHEST PRIORITY)
                        # ============================================
                        if HAS_SAFETY and safety_guard:
                            is_dangerous, danger_reason = safety_guard.scan_for_critical_danger(current_content)
                            
                            if is_dangerous:
                                self.logger.warning(f"⛔ HARD BLOCK: {danger_reason}")
                                # FORCE ALERT (Score 1.0) - overrides everything
                                self.trigger_alert(1.0, self.last_content, current_content)
                                self.last_content = current_content
                                time.sleep(self.interval)
                                continue
                        
                        # ============================================
                        # TR-07: SHRINKAGE CHECK (Paranoia Mode)
                        # ============================================
                        len_old = len(self.last_content)
                        len_new = len(current_content)
                        
                        multiplier = 1.0
                        if len_new < (len_old * 0.5) and len_new > 10:
                            self.logger.warning(f"📉 SHRINKAGE DETECTED: {len_old} -> {len_new} chars")
                            multiplier = 2.0
                        
                        # ============================================
                        # DRIFT CHECK (Semantic Analysis)
                        # ============================================
                        if HAS_DRIFT and drift_monitor and drift_monitor.is_ready:
                            if len(current_content) >= 20 and len(self.last_content) >= 20:
                                raw_score = drift_monitor.calculate_drift_score(self.last_content, current_content)
                                final_score = raw_score * multiplier
                                
                                if multiplier > 1.0:
                                    self.logger.info(f"🕵️ PARANOIA: {raw_score:.2f} × {multiplier} = {final_score:.2f}")
                                
                                if final_score > self.base_threshold:
                                    self.trigger_alert(final_score, self.last_content, current_content)
                                else:
                                    self.logger.info(f"✅ Safe Update (Drift: {final_score:.2f})")
                    
                    self.last_content = current_content
                
                time.sleep(self.interval)
            except Exception as e:
                self.logger.error(f"Sentinel error: {e}")
                time.sleep(self.interval)

    def trigger_alert(self, score: float, old: str, new: str):
        """Put a request into the UI queue for main thread handling."""
        if self.ui_queue:
            self.logger.info(f"🚨 ALERT ({score:.2f}) -> Signaling Main Thread")
            self.last_trigger_time = time.time()
            
            self.ui_queue.put({
                'type': 'SHOW_UI',
                'score': score,
                'old': old,
                'new': new
            })
        else:
            print(f"\n🚨 DRIFT DETECTED ({score:.2f}) - UI Queue not connected!")
    
    def stop(self):
        """Stop the sentinel loop."""
        self.is_active = False


# Global Instance
sentinel = ClipboardSentinel()
