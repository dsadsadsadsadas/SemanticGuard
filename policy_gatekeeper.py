#!/usr/bin/env python3
"""
🎭 TREPAN Policy Gatekeeper (TR-04 + TR-06 + TR-10 + TR-10.5)
The "Legislator" UI - pops up when drift is detected.

TR-06: Reads actual GEMINI.md from disk for accurate context display.
TR-10: Displays Phase Banner based on detected development phase.
TR-10.5: Displays Invariant Violation Explanation.
"""

import tkinter as tk
from tkinter import ttk
import logging
import os

try:
    from context_manager import context_db, GEMINI_FILE
    HAS_CONTEXT = True
except ImportError:
    HAS_CONTEXT = False
    context_db = None
    GEMINI_FILE = "GEMINI.md"

# TR-10: Import phase detector
try:
    from phase_detector import phase_detector
    HAS_PHASE = True
except ImportError:
    HAS_PHASE = False
    phase_detector = None

# TR-10.5: Import invariant explainer
try:
    from invariant_explainer import explainer
    HAS_EXPLAINER = True
except ImportError:
    HAS_EXPLAINER = False
    explainer = None


class DiamondGatekeeper:
    """
    Tkinter popup window for drift decisions.
    Shows code diff, phase banner, explanation, and collects intent information.
    """
    
    def __init__(self, drift_score: float, old_text: str, new_text: str, 
                 regex_hits: list = None, shrinkage_ratio: float = 1.0):
        self.score = drift_score
        self.old_text = old_text
        self.new_text = new_text
        self.regex_hits = regex_hits or []
        self.shrinkage_ratio = shrinkage_ratio
        self.result = "IGNORE"
        self.entry_law = None
        self.entry_why = None
        self.phase_context = None
        self.explanation = None  # TR-10.5
        self.logger = logging.getLogger("Trepan.Gatekeeper")

    def _get_phase_context(self) -> dict:
        """TR-10: Get current phase from detector."""
        if HAS_PHASE and phase_detector:
            try:
                return phase_detector.get_current_phase()
            except Exception as e:
                self.logger.warning(f"Phase detection failed: {e}")
        
        return {
            "phase_name": "NORMAL_FLOW",
            "icon": "📋",
            "confidence": 1.0,
            "description": "Standard working mode.",
            "recommended_threshold": 0.4,
            "silent_mode": True,
            "signals": []
        }

    def _get_explanation(self) -> str:
        """TR-10.5: Get human-readable explanation for this alert."""
        if HAS_EXPLAINER and explainer:
            try:
                event_context = {
                    "phase": self.phase_context.get("phase_name", "NORMAL_FLOW"),
                    "drift_score": self.score,
                    "shrinkage_ratio": self.shrinkage_ratio,
                    "regex_hits": self.regex_hits,
                    "lane": "LOUD",
                    "tags": []  # Could be enhanced with tag detection
                }
                return explainer.explain(event_context)
            except Exception as e:
                self.logger.warning(f"Explanation generation failed: {e}")
        
        return "Change requires manual review before proceeding."

    def _read_current_gemini_context(self) -> str:
        """TR-06: Reads the actual GEMINI.md file from disk."""
        if os.path.exists(GEMINI_FILE):
            try:
                with open(GEMINI_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                    if len(content) > 2000:
                        return "...(Previous content truncated)...\n" + content[-2000:]
                    return content
            except Exception as e:
                return f"[Error reading GEMINI.md: {e}]"
        return "[New File - No Context Yet]"

    def show(self):
        """
        Launch the UI and block until a decision is made.
        Returns: (action, law_text, why_text)
        """
        # TR-10: Get phase context before building UI
        self.phase_context = self._get_phase_context()
        
        # TR-10.5: Get explanation
        self.explanation = self._get_explanation()
        
        root = tk.Tk()
        root.title(f"💎 Trepan Legislator (Drift: {self.score:.2f})")
        root.geometry("920x800")
        root.configure(bg="#1a1a2e")
        
        # Force on top and focus
        root.attributes("-topmost", True)
        root.focus_force()
        
        # ========== TR-10: PHASE BANNER ==========
        phase_frame = tk.Frame(root, bg=self._get_phase_bg_color())
        phase_frame.pack(fill=tk.X, pady=(0, 2))
        
        phase_text = f"{self.phase_context['icon']} {self.phase_context['phase_name']} PHASE"
        if self.phase_context['confidence'] < 1.0:
            phase_text += f" (Confidence: {int(self.phase_context['confidence'] * 100)}%)"
        
        tk.Label(
            phase_frame,
            text=phase_text,
            font=("Segoe UI", 11, "bold"),
            fg=self._get_phase_fg_color(),
            bg=self._get_phase_bg_color()
        ).pack(pady=5)
        
        # ========== TR-10.5: EXPLANATION BANNER ==========
        explain_frame = tk.Frame(root, bg="#2d1f1f")
        explain_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        tk.Label(
            explain_frame,
            text="⚠️ INVARIANT VIOLATION",
            font=("Segoe UI", 10, "bold"),
            fg="#fbbf24",
            bg="#2d1f1f"
        ).pack(pady=(5, 2))
        
        # Wrap explanation text
        explain_label = tk.Label(
            explain_frame,
            text=self.explanation,
            font=("Segoe UI", 10),
            fg="#e0e0e0",
            bg="#2d1f1f",
            wraplength=850,
            justify=tk.LEFT
        )
        explain_label.pack(pady=(0, 8), padx=10)
        
        # ========== HEADER ==========
        header_frame = tk.Frame(root, bg="#16213e")
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            header_frame, 
            text="🛡️ CONTEXT INTERVENTION REQUEST", 
            font=("Segoe UI", 14, "bold"), 
            fg="#ff6b6b", 
            bg="#16213e"
        ).pack(pady=10)
        
        tk.Label(
            header_frame,
            text=f"Drift Score: {self.score:.2f} | Threshold: {self.phase_context['recommended_threshold']}",
            font=("Segoe UI", 10),
            fg="#a0a0a0",
            bg="#16213e"
        ).pack()

        # ========== COMPARISON VIEW ==========
        diff_frame = tk.Frame(root, bg="#1a1a2e")
        diff_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # LEFT: The Real GEMINI.md
        left_frame = tk.LabelFrame(
            diff_frame, 
            text=" [Disk] Current GEMINI.md ", 
            padx=5, pady=5,
            font=("Segoe UI", 10),
            fg="#888888",
            bg="#1a1a2e"
        )
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        txt_current = tk.Text(
            left_frame, height=10, width=40, 
            font=("Consolas", 9), 
            bg="#0d1b2a", fg="#e0e0e0",
            insertbackground="white"
        )
        real_file_content = self._read_current_gemini_context()
        txt_current.insert(tk.END, real_file_content)
        txt_current.config(state=tk.DISABLED)
        txt_current.pack(fill=tk.BOTH, expand=True)

        # RIGHT: The Proposal (New Clipboard Content)
        right_frame = tk.LabelFrame(
            diff_frame, 
            text=" [Buffer] New Clipboard Content ", 
            padx=5, pady=5,
            font=("Segoe UI", 10),
            fg="#4fc3f7",
            bg="#1a1a2e"
        )
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        txt_new = tk.Text(
            right_frame, height=10, width=40, 
            font=("Consolas", 9), 
            bg="#0d1b2a", fg="#4ade80",
            insertbackground="white"
        )
        txt_new.insert(tk.END, self.new_text[:3000])
        txt_new.config(state=tk.DISABLED)
        txt_new.pack(fill=tk.BOTH, expand=True)

        # ========== THE LEGISLATOR (Inputs) ==========
        input_frame = tk.LabelFrame(
            root, 
            text=" 💎 Mint New Diamond (Define Intent) ", 
            padx=10, pady=10,
            font=("Segoe UI", 10, "bold"),
            fg="#ffd93d",
            bg="#1a1a2e"
        )
        input_frame.pack(fill=tk.X, padx=15, pady=10)

        tk.Label(
            input_frame, 
            text="⚖️ The Law (What rule does this enforce?):",
            font=("Segoe UI", 9),
            fg="#e0e0e0",
            bg="#1a1a2e"
        ).pack(anchor=tk.W)
        
        self.entry_law = tk.Entry(
            input_frame, font=("Segoe UI", 10),
            bg="#0d1b2a", fg="#ffffff",
            insertbackground="white"
        )
        self.entry_law.insert(0, "Enforce...")
        self.entry_law.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            input_frame, 
            text="🤔 The Why (Reasoning/Context):",
            font=("Segoe UI", 9),
            fg="#e0e0e0",
            bg="#1a1a2e"
        ).pack(anchor=tk.W)
        
        self.entry_why = tk.Entry(
            input_frame, font=("Segoe UI", 10),
            bg="#0d1b2a", fg="#ffffff",
            insertbackground="white"
        )
        self.entry_why.insert(0, "To prevent...")
        self.entry_why.pack(fill=tk.X)

        # ========== ACTION BUTTONS ==========
        btn_frame = tk.Frame(root, bg="#1a1a2e")
        btn_frame.pack(pady=15)

        tk.Button(
            btn_frame, text="⛔ BLOCK", 
            bg="#ef4444", fg="white",
            font=("Segoe UI", 10, "bold"),
            width=12, height=2, cursor="hand2",
            command=lambda: self._finish(root, "BLOCK")
        ).pack(side=tk.LEFT, padx=8)

        tk.Button(
            btn_frame, text="🤷 IGNORE", 
            bg="#6b7280", fg="white",
            font=("Segoe UI", 10), width=12, height=2, cursor="hand2",
            command=lambda: self._finish(root, "IGNORE")
        ).pack(side=tk.LEFT, padx=8)

        tk.Button(
            btn_frame, text="💎 MINT DIAMOND", 
            bg="#10b981", fg="white",
            font=("Segoe UI", 11, "bold"),
            width=18, height=2, cursor="hand2",
            command=lambda: self._finish(root, "COMMIT")
        ).pack(side=tk.LEFT, padx=8)

        root.protocol("WM_DELETE_WINDOW", lambda: self._finish(root, "IGNORE"))
        root.mainloop()
        
        law_text = self.entry_law.get() if self.entry_law else ""
        why_text = self.entry_why.get() if self.entry_why else ""
        
        return self.result, law_text, why_text

    def _get_phase_bg_color(self) -> str:
        """Get background color for phase banner."""
        colors = {
            "HARDENING": "#3d1a1a",
            "PROTOTYPING": "#1a2d1a",
            "DEBUGGING": "#2d2a1a",
            "NORMAL_FLOW": "#1a1a2e"
        }
        return colors.get(self.phase_context.get("phase_name", "NORMAL_FLOW"), "#1a1a2e")
    
    def _get_phase_fg_color(self) -> str:
        """Get foreground color for phase banner."""
        colors = {
            "HARDENING": "#ff6b6b",
            "PROTOTYPING": "#4ade80",
            "DEBUGGING": "#fbbf24",
            "NORMAL_FLOW": "#a0a0a0"
        }
        return colors.get(self.phase_context.get("phase_name", "NORMAL_FLOW"), "#a0a0a0")

    def _finish(self, root, action):
        """Handle button click and close window."""
        self.result = action
        root.destroy()
    
    def get_phase_context(self) -> dict:
        """TR-10: Return the phase context for external use."""
        return self.phase_context
    
    def get_explanation(self) -> str:
        """TR-10.5: Return the explanation for external use."""
        return self.explanation


def launch_gatekeeper(score: float, old: str, new: str, 
                      regex_hits: list = None, shrinkage_ratio: float = 1.0):
    """
    Helper function to instantiate and show the gatekeeper window.
    
    Args:
        score: Drift score
        old: Previous clipboard content
        new: New clipboard content
        regex_hits: List of regex pattern matches (TR-10.5)
        shrinkage_ratio: new_len / old_len ratio (TR-10.5)
    
    Returns:
        Tuple: (action, law_text, why_text)
    """
    try:
        window = DiamondGatekeeper(score, old, new, regex_hits, shrinkage_ratio)
        result = window.show()
        return result
    except Exception as e:
        logging.error(f"Gatekeeper UI failed: {e}")
        return "IGNORE", "", ""
