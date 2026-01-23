#!/usr/bin/env python3
"""
🎭 TREPAN Policy Gatekeeper (TR-04 + TR-06)
The "Legislator" UI - pops up when drift is detected.

TR-06: Now reads the ACTUAL GEMINI.md file from disk for accurate context display.
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


class DiamondGatekeeper:
    """
    Tkinter popup window for drift decisions.
    Shows code diff and collects intent information.
    """
    
    def __init__(self, drift_score: float, old_text: str, new_text: str):
        self.score = drift_score
        self.old_text = old_text
        self.new_text = new_text
        self.result = "IGNORE"
        self.entry_law = None
        self.entry_why = None
        self.logger = logging.getLogger("Trepan.Gatekeeper")

    def _read_current_gemini_context(self) -> str:
        """
        TR-06: Reads the actual GEMINI.md file from disk to show fresh context.
        """
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
        root = tk.Tk()
        root.title(f"💎 Trepan Legislator (Drift: {self.score:.2f})")
        root.geometry("900x700")
        root.configure(bg="#1a1a2e")
        
        # Force on top and focus
        root.attributes("-topmost", True)
        root.focus_force()
        
        # --- HEADER ---
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
            text=f"Drift Score: {self.score:.2f} (Threshold: 0.40)",
            font=("Segoe UI", 10),
            fg="#a0a0a0",
            bg="#16213e"
        ).pack()

        # --- COMPARISON VIEW (Side by Side) ---
        diff_frame = tk.Frame(root, bg="#1a1a2e")
        diff_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # LEFT: The Real GEMINI.md
        left_frame = tk.LabelFrame(
            diff_frame, 
            text=" [Disk] Current GEMINI.md ", 
            padx=5, 
            pady=5,
            font=("Segoe UI", 10),
            fg="#888888",
            bg="#1a1a2e"
        )
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        txt_current = tk.Text(
            left_frame, 
            height=15, 
            width=40, 
            font=("Consolas", 9), 
            bg="#0d1b2a",
            fg="#e0e0e0",
            insertbackground="white"
        )
        
        # TR-06: Load Fresh Content from Disk
        real_file_content = self._read_current_gemini_context()
        txt_current.insert(tk.END, real_file_content)
        txt_current.config(state=tk.DISABLED)
        txt_current.pack(fill=tk.BOTH, expand=True)

        # RIGHT: The Proposal (New Clipboard Content)
        right_frame = tk.LabelFrame(
            diff_frame, 
            text=" [Buffer] New Clipboard Content ", 
            padx=5, 
            pady=5,
            font=("Segoe UI", 10),
            fg="#4fc3f7",
            bg="#1a1a2e"
        )
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        txt_new = tk.Text(
            right_frame, 
            height=15, 
            width=40, 
            font=("Consolas", 9), 
            bg="#0d1b2a",
            fg="#4ade80",
            insertbackground="white"
        )
        txt_new.insert(tk.END, self.new_text[:3000])  # Truncate for display
        txt_new.config(state=tk.DISABLED)
        txt_new.pack(fill=tk.BOTH, expand=True)

        # --- THE LEGISLATOR (Inputs) ---
        input_frame = tk.LabelFrame(
            root, 
            text=" 💎 Mint New Diamond (Define Intent) ", 
            padx=10, 
            pady=10,
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
            input_frame, 
            font=("Segoe UI", 10),
            bg="#0d1b2a",
            fg="#ffffff",
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
            input_frame, 
            font=("Segoe UI", 10),
            bg="#0d1b2a",
            fg="#ffffff",
            insertbackground="white"
        )
        self.entry_why.insert(0, "To prevent...")
        self.entry_why.pack(fill=tk.X)

        # --- ACTION BUTTONS ---
        btn_frame = tk.Frame(root, bg="#1a1a2e")
        btn_frame.pack(pady=15)

        # BLOCK Button
        tk.Button(
            btn_frame, 
            text="⛔ BLOCK", 
            bg="#ef4444", 
            fg="white",
            font=("Segoe UI", 10, "bold"),
            width=12, 
            height=2,
            cursor="hand2",
            command=lambda: self._finish(root, "BLOCK")
        ).pack(side=tk.LEFT, padx=8)

        # IGNORE Button
        tk.Button(
            btn_frame, 
            text="🤷 IGNORE", 
            bg="#6b7280",
            fg="white",
            font=("Segoe UI", 10),
            width=12, 
            height=2,
            cursor="hand2",
            command=lambda: self._finish(root, "IGNORE")
        ).pack(side=tk.LEFT, padx=8)

        # MINT DIAMOND Button
        tk.Button(
            btn_frame, 
            text="💎 MINT DIAMOND", 
            bg="#10b981", 
            fg="white",
            font=("Segoe UI", 11, "bold"),
            width=18, 
            height=2,
            cursor="hand2",
            command=lambda: self._finish(root, "COMMIT")
        ).pack(side=tk.LEFT, padx=8)

        # Handle window close
        root.protocol("WM_DELETE_WINDOW", lambda: self._finish(root, "IGNORE"))
        
        root.mainloop()
        
        law_text = self.entry_law.get() if self.entry_law else ""
        why_text = self.entry_why.get() if self.entry_why else ""
        
        return self.result, law_text, why_text

    def _finish(self, root, action):
        """Handle button click and close window."""
        self.result = action
        root.destroy()


def launch_gatekeeper(score: float, old: str, new: str):
    """
    Helper function to instantiate and show the gatekeeper window.
    
    Args:
        score: Drift score
        old: Previous clipboard content
        new: New clipboard content
        
    Returns:
        Tuple: (action, law_text, why_text)
    """
    try:
        window = DiamondGatekeeper(score, old, new)
        return window.show()
    except Exception as e:
        logging.error(f"Gatekeeper UI failed: {e}")
        return "IGNORE", "", ""
