#!/usr/bin/env python3
"""
🛡️ TREPAN Policy UI (policy_ui.py)
Transparent Diff Viewer for Context Injection Consent

Instead of silently modifying the clipboard (trust violation),
this module shows the user what Trepan wants to inject and asks for consent.

Features:
- Side-by-side diff view: "Original" vs "With Trepan Context"
- Accept/Reject buttons
- Keyboard shortcuts: Enter=Accept, Escape=Reject
- Auto-timeout option for power users
"""

import tkinter as tk
from tkinter import ttk
import difflib
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum
import threading


class PolicyDecision(Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    TIMEOUT = "timeout"


@dataclass
class InjectionProposal:
    """Represents a proposed context injection."""
    original_content: str
    proposed_content: str
    context_type: str  # e.g., "Security Context", "Project Map", etc.
    source: str  # e.g., "GEMINI.md update", "Red Team finding"


class PolicyDiffViewer:
    """
    A transparent diff viewer popup that shows the user what Trepan
    proposes to inject vs the original content.
    """
    
    def __init__(self, auto_accept_timeout: Optional[int] = None):
        """
        Args:
            auto_accept_timeout: Seconds before auto-accepting (None = no timeout)
        """
        self.auto_accept_timeout = auto_accept_timeout
        self.decision: Optional[PolicyDecision] = None
        self.root: Optional[tk.Tk] = None
        self._timer_id = None
        self._countdown = 0
        
    def show_diff(self, proposal: InjectionProposal) -> PolicyDecision:
        """
        Show the diff dialog and wait for user decision.
        This blocks until the user makes a choice.
        
        Returns:
            PolicyDecision: ACCEPT, REJECT, or TIMEOUT
        """
        self.decision = None
        self._countdown = self.auto_accept_timeout or 0
        
        # Create root window
        self.root = tk.Tk()
        self.root.title("🛡️ Trepan - Paste with Policy")
        self.root.geometry("900x600")
        self.root.configure(bg="#1a1a2e")
        
        # Center on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - 450
        y = (self.root.winfo_screenheight() // 2) - 300
        self.root.geometry(f"+{x}+{y}")
        
        # Keep on top
        self.root.attributes("-topmost", True)
        
        # Configure styles
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Header.TLabel", 
                        background="#1a1a2e", 
                        foreground="#eee", 
                        font=("Segoe UI", 14, "bold"))
        style.configure("Sub.TLabel", 
                        background="#1a1a2e", 
                        foreground="#888", 
                        font=("Segoe UI", 10))
        style.configure("Accept.TButton", 
                        font=("Segoe UI", 11, "bold"),
                        padding=10)
        style.configure("Reject.TButton", 
                        font=("Segoe UI", 11),
                        padding=10)
        
        # Header
        header_frame = tk.Frame(self.root, bg="#1a1a2e")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        title = ttk.Label(header_frame, 
                          text="🛡️ Trepan Context Injection Request",
                          style="Header.TLabel")
        title.pack(anchor="w")
        
        subtitle = ttk.Label(header_frame,
                             text=f"Type: {proposal.context_type} | Source: {proposal.source}",
                             style="Sub.TLabel")
        subtitle.pack(anchor="w", pady=(5, 0))
        
        # Diff panels container
        panels_frame = tk.Frame(self.root, bg="#1a1a2e")
        panels_frame.pack(fill="both", expand=True, padx=20, pady=10)
        panels_frame.columnconfigure(0, weight=1)
        panels_frame.columnconfigure(1, weight=1)
        panels_frame.rowconfigure(0, weight=1)
        
        # Original panel (left)
        orig_frame = tk.LabelFrame(panels_frame, 
                                    text=" 📋 Original Content ",
                                    bg="#16213e", 
                                    fg="#eee",
                                    font=("Segoe UI", 10, "bold"))
        orig_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        orig_text = tk.Text(orig_frame, 
                           wrap="word",
                           bg="#0f0f23",
                           fg="#cccccc",
                           insertbackground="#fff",
                           font=("Consolas", 10),
                           padx=10,
                           pady=10,
                           relief="flat")
        orig_text.pack(fill="both", expand=True, padx=5, pady=5)
        orig_text.insert("1.0", self._truncate(proposal.original_content))
        orig_text.config(state="disabled")
        
        # Proposed panel (right)
        prop_frame = tk.LabelFrame(panels_frame, 
                                    text=" ✨ With Trepan Context ",
                                    bg="#16213e", 
                                    fg="#00ff88",
                                    font=("Segoe UI", 10, "bold"))
        prop_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        
        prop_text = tk.Text(prop_frame, 
                           wrap="word",
                           bg="#0f0f23",
                           fg="#cccccc",
                           insertbackground="#fff",
                           font=("Consolas", 10),
                           padx=10,
                           pady=10,
                           relief="flat")
        prop_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Insert with highlighting for added content
        self._insert_highlighted(prop_text, 
                                 proposal.original_content, 
                                 proposal.proposed_content)
        prop_text.config(state="disabled")
        
        # Button frame
        btn_frame = tk.Frame(self.root, bg="#1a1a2e")
        btn_frame.pack(fill="x", padx=20, pady=(10, 20))
        
        # Timer label (if auto-accept enabled)
        self.timer_label = None
        if self.auto_accept_timeout:
            self.timer_label = ttk.Label(btn_frame,
                                         text=f"Auto-accepting in {self._countdown}s...",
                                         style="Sub.TLabel")
            self.timer_label.pack(side="left")
            self._start_countdown()
        
        # Buttons
        reject_btn = tk.Button(btn_frame, 
                               text="✕ Reject (Esc)",
                               command=self._on_reject,
                               bg="#e74c3c",
                               fg="white",
                               activebackground="#c0392b",
                               activeforeground="white",
                               font=("Segoe UI", 11),
                               relief="flat",
                               padx=20,
                               pady=8,
                               cursor="hand2")
        reject_btn.pack(side="right", padx=(10, 0))
        
        accept_btn = tk.Button(btn_frame, 
                               text="✓ Accept (Enter)",
                               command=self._on_accept,
                               bg="#27ae60",
                               fg="white",
                               activebackground="#1e8449",
                               activeforeground="white",
                               font=("Segoe UI", 11, "bold"),
                               relief="flat",
                               padx=20,
                               pady=8,
                               cursor="hand2")
        accept_btn.pack(side="right")
        
        # Keyboard bindings
        self.root.bind("<Return>", lambda e: self._on_accept())
        self.root.bind("<Escape>", lambda e: self._on_reject())
        self.root.bind("<Alt-F4>", lambda e: self._on_reject())
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_reject)
        
        # Run the dialog
        self.root.mainloop()
        
        return self.decision or PolicyDecision.REJECT
    
    def _truncate(self, text: str, max_chars: int = 3000) -> str:
        """Truncate long content for display."""
        if len(text) > max_chars:
            return text[:max_chars] + f"\n\n... [truncated {len(text) - max_chars} more characters]"
        return text
    
    def _insert_highlighted(self, text_widget: tk.Text, 
                           original: str, 
                           proposed: str):
        """Insert text with highlighting for additions."""
        # Configure tags for highlighting
        text_widget.tag_configure("added", 
                                  background="#1a4d1a", 
                                  foreground="#00ff88")
        text_widget.tag_configure("normal", 
                                  foreground="#cccccc")
        
        # Use difflib to find changes
        orig_lines = original.split('\n')
        prop_lines = proposed.split('\n')
        
        differ = difflib.Differ()
        diff = list(differ.compare(orig_lines, prop_lines))
        
        for line in diff:
            if line.startswith('+ '):
                # Added line
                text_widget.insert("end", line[2:] + '\n', "added")
            elif line.startswith('  '):
                # Unchanged line
                text_widget.insert("end", line[2:] + '\n', "normal")
            elif line.startswith('? '):
                # Skip diff markers
                continue
            # We skip '- ' lines (removed) since we're showing the proposed version
    
    def _start_countdown(self):
        """Start the auto-accept countdown timer."""
        if self._countdown > 0:
            self.timer_label.config(text=f"Auto-accepting in {self._countdown}s...")
            self._countdown -= 1
            self._timer_id = self.root.after(1000, self._start_countdown)
        else:
            self._on_timeout()
    
    def _on_accept(self):
        """Handle accept button/key."""
        self.decision = PolicyDecision.ACCEPT
        self._cleanup()
    
    def _on_reject(self):
        """Handle reject button/key."""
        self.decision = PolicyDecision.REJECT
        self._cleanup()
    
    def _on_timeout(self):
        """Handle auto-accept timeout."""
        self.decision = PolicyDecision.TIMEOUT
        self._cleanup()
    
    def _cleanup(self):
        """Clean up and close the window."""
        if self._timer_id:
            self.root.after_cancel(self._timer_id)
        if self.root:
            self.root.quit()
            self.root.destroy()


def show_policy_dialog(original: str, 
                       proposed: str,
                       context_type: str = "Context Injection",
                       source: str = "Trepan",
                       auto_timeout: Optional[int] = None) -> PolicyDecision:
    """
    Convenience function to show the policy dialog.
    
    Args:
        original: The original clipboard content
        proposed: The proposed modified content
        context_type: Type of context being injected
        source: Source of the injection
        auto_timeout: Seconds before auto-accept (None = manual only)
    
    Returns:
        PolicyDecision: The user's decision
    """
    proposal = InjectionProposal(
        original_content=original,
        proposed_content=proposed,
        context_type=context_type,
        source=source
    )
    
    viewer = PolicyDiffViewer(auto_accept_timeout=auto_timeout)
    return viewer.show_diff(proposal)


# --- DEMO ---
if __name__ == "__main__":
    original = """def login(username, password):
    # TODO: Add authentication
    return True"""
    
    proposed = """# 🛡️ TREPAN SECURITY CONTEXT
# File: auth.py | Warning: Hardcoded auth detected

def login(username, password):
    # TODO: Add authentication
    return True

# CONSTRAINT: Implement proper password hashing with bcrypt"""
    
    result = show_policy_dialog(
        original=original,
        proposed=proposed,
        context_type="Security Warning",
        source="AST Engine Detection",
        auto_timeout=None  # Set to 10 for 10-second auto-accept
    )
    
    print(f"\n✅ Decision: {result.value}")
