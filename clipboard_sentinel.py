#!/usr/bin/env python3
"""
🛡️ TREPAN Clipboard Sentinel (TR-03 + TR-05 + TR-06 + TR-07 + TR-08 + TR-09)
Semantic Firewall: Wires the Drift Engine into clipboard monitoring.

TR-05: Thread-safe UI launching via Queue.
TR-06: Cooldown timer + Image detection skip.
TR-07: Shrinkage Detector (Paranoia Mode).
TR-08: Hardened Safety Heuristics (Hard Block).
TR-09: Silent Mode & Draft Ledger (Dual-Lane Architecture).
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

# TR-09: Import ledger manager for silent mode
try:
    from ledger_manager import ledger
    HAS_LEDGER = True
except ImportError:
    HAS_LEDGER = False
    ledger = None


# ============================================
# THRESHOLDS (TR-09 Dual-Lane Architecture)
# ============================================
CRITICAL_THRESHOLD = 0.8   # LOUD LANE: Blocking popup
MEDIUM_THRESHOLD = 0.4     # SILENT LANE: Log to ledger


class ClipboardSentinel:
    """
    Monitors clipboard for semantic drift and critical security patterns.
    Uses a dual-lane architecture:
    - LOUD LANE: Blocking UI for critical threats
    - SILENT LANE: Background logging for medium drift
    """
    
    def __init__(self, check_interval: float = 1.0, drift_threshold: float = MEDIUM_THRESHOLD):
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
        if HAS_LEDGER:
            self.logger.info("[*] Silent Mode ENABLED (TR-09)")
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
        """
        Main monitoring loop with TR-09 Dual-Lane Architecture.
        
        LOUD LANE (Blocking UI):
        - Hard regex match (TR-08)
        - Shrinkage detected (TR-07)
        - Drift > 0.8 (Critical)
        
        SILENT LANE (Ledger):
        - Drift 0.4 - 0.79 (Medium)
        """
        self.logger.info("[*] Clipboard Sentinel: WATCHING")
        
        # Prune stale entries on startup (TR-09)
        if HAS_LEDGER and ledger:
            ledger.prune_stale_entries()
        
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
                        self._analyze_and_route(current_content)
                    
                    self.last_content = current_content
                
                time.sleep(self.interval)
            except Exception as e:
                self.logger.error(f"Sentinel error: {e}")
                time.sleep(self.interval)

    def _analyze_and_route(self, current_content: str):
        """
        TR-09: The Traffic Controller
        Analyzes content and routes to appropriate lane.
        """
        # ============================================
        # STEP A: HARD CHECKS (Always LOUD)
        # ============================================
        
        # A1: TR-08 - Regex Safety Check
        if HAS_SAFETY and safety_guard:
            is_dangerous, danger_reason = safety_guard.scan_for_critical_danger(current_content)
            
            if is_dangerous:
                self.logger.warning(f"⛔ HARD BLOCK (Regex): {danger_reason}")
                self._trigger_loud_alert(1.0, self.last_content, current_content)
                return
        
        # A2: TR-07 - Shrinkage Detection
        len_old = len(self.last_content)
        len_new = len(current_content)
        multiplier = 1.0
        shrinkage_detected = False
        
        if len_new < (len_old * 0.5) and len_new > 10:
            self.logger.warning(f"📉 SHRINKAGE: {len_old} -> {len_new} chars")
            multiplier = 2.0
            shrinkage_detected = True
            # Shrinkage alone forces LOUD lane
            # (Continue to calculate drift for the score)
        
        # ============================================
        # STEP B: DRIFT ANALYSIS
        # ============================================
        if not HAS_DRIFT or not drift_monitor or not drift_monitor.is_ready:
            return
        
        if len(current_content) < 20 or len(self.last_content) < 20:
            return  # Too short for meaningful analysis
        
        raw_score = drift_monitor.calculate_drift_score(self.last_content, current_content)
        final_score = raw_score * multiplier
        
        if multiplier > 1.0:
            self.logger.info(f"🕵️ PARANOIA: {raw_score:.2f} × {multiplier} = {final_score:.2f}")
        
        # ============================================
        # STEP C: TRAFFIC ROUTING (TR-09)
        # ============================================
        
        # C1: LOUD LANE - Critical or Shrinkage
        if final_score > CRITICAL_THRESHOLD or shrinkage_detected:
            self.logger.info(f"🔊 LOUD LANE: Score {final_score:.2f}")
            self._trigger_loud_alert(final_score, self.last_content, current_content)
        
        # C2: SILENT LANE - Medium Drift
        elif final_score > MEDIUM_THRESHOLD:
            self.logger.info(f"🔇 SILENT LANE: Score {final_score:.2f}")
            self._trigger_silent_log(final_score, self.last_content, current_content, multiplier)
        
        # C3: SAFE - Below Threshold
        else:
            self.logger.info(f"✅ SAFE: Score {final_score:.2f}")

    def _trigger_loud_alert(self, score: float, old: str, new: str):
        """
        LOUD LANE: Blocking UI popup.
        Used for critical threats, shrinkage, and high drift.
        """
        if self.ui_queue:
            self.logger.info(f"🚨 LOUD ALERT ({score:.2f}) -> Blocking UI")
            self.last_trigger_time = time.time()
            
            self.ui_queue.put({
                'type': 'SHOW_UI',
                'score': score,
                'old': old,
                'new': new
            })
        else:
            print(f"\n🚨 CRITICAL ALERT ({score:.2f}) - UI Queue not connected!")

    def _trigger_silent_log(self, score: float, old: str, new: str, multiplier: float = 1.0):
        """
        SILENT LANE: Background logging without user interruption.
        Used for medium drift (0.4-0.79).
        """
        if HAS_LEDGER and ledger:
            entry_id = ledger.log_event(score, old, new, multiplier)
            print(f"[+] Silent Draft Logged: {entry_id} (Score: {score:.2f})")
        else:
            self.logger.warning(f"📝 Would log silently (Score: {score:.2f}) but ledger not available")
    
    def stop(self):
        """Stop the sentinel loop."""
        self.is_active = False


# Global Instance
sentinel = ClipboardSentinel()
