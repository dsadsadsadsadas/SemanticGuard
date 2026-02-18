#!/usr/bin/env python3
"""
📒 TREPAN Ledger Manager (TR-09)
Manages the Draft Ledger for Silent Mode operations.

Silent Mode logs medium-drift events (0.4-0.79) without blocking the user.
The ledger can be reviewed later via `trepan --review`.
"""

import os
import json
import uuid
import hashlib
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

LEDGER_FILE = "draft_ledger.json"
MAX_ENTRIES = 200
STALE_HOURS = 24


class LedgerManager:
    """
    Thread-safe manager for the draft ledger.
    Handles logging, pruning, and review of silent mode events.
    """
    
    def __init__(self, ledger_path: str = LEDGER_FILE):
        self.ledger_path = ledger_path
        self.logger = logging.getLogger("Trepan.Ledger")
        self._lock = threading.Lock()
        self._ensure_ledger_exists()
    
    def _ensure_ledger_exists(self):
        """Create ledger file with empty structure if it doesn't exist."""
        if not os.path.exists(self.ledger_path):
            self._write_ledger(self._empty_ledger())
    
    def _empty_ledger(self) -> dict:
        """Return empty ledger structure."""
        return {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "last_modified": datetime.now().isoformat(),
            "entries": [],
            "session_stats": {
                "total_events": 0,
                "approved": 0,
                "rejected": 0,
                "pending": 0
            }
        }
    
    def _read_ledger(self) -> dict:
        """Safely read the ledger file."""
        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return self._empty_ledger()
    
    def _write_ledger(self, data: dict):
        """
        Atomically write the ledger file.
        Uses write-to-temp-then-rename for crash safety.
        """
        temp_path = self.ledger_path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # Atomic rename (on most filesystems)
            os.replace(temp_path, self.ledger_path)
        except Exception as e:
            self.logger.error(f"Failed to write ledger: {e}")
            # Cleanup temp file if it exists
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
    
    def _hash_content(self, content: str) -> str:
        """Generate SHA256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    
    def _extract_tags(self, content: str) -> List[str]:
        """
        Extract simple semantic tags from content.
        Uses keyword heuristics for categorization.
        """
        tags = []
        content_lower = content.lower()
        
        tag_patterns = {
            "import": ["import ", "from "],
            "function": ["def ", "function ", "async def "],
            "class": ["class "],
            "security": ["password", "secret", "key", "token", "auth"],
            "database": ["sql", "query", "select", "insert", "database"],
            "api": ["request", "response", "endpoint", "http"],
            "error": ["error", "exception", "try:", "except", "catch"],
            "test": ["test_", "assert", "mock", "pytest"],
            "config": ["config", "settings", "env", ".env"],
        }
        
        for tag, patterns in tag_patterns.items():
            if any(p in content_lower for p in patterns):
                tags.append(tag)
        
        return tags[:5]  # Max 5 tags
    
    def _get_active_window(self) -> str:
        """
        Attempt to get the active window title.
        Returns "Unknown" if detection fails.
        """
        try:
            import subprocess
            # Windows-specific: Get active window title
            result = subprocess.run(
                ['powershell', '-Command', 
                 '(Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -First 1).MainWindowTitle'],
                capture_output=True, text=True, timeout=1
            )
            title = result.stdout.strip()
            return title if title else "Unknown"
        except Exception:
            return "Unknown"
    
    def log_event(
        self, 
        score: float, 
        old_text: str, 
        new_text: str, 
        multiplier: float = 1.0
    ) -> str:
        """
        Log a silent mode event to the ledger.
        
        Args:
            score: The final drift score
            old_text: Previous clipboard content
            new_text: New clipboard content
            multiplier: Paranoia multiplier applied
            
        Returns:
            The ID of the new entry
        """
        entry_id = f"draft-{uuid.uuid4().hex[:8]}"
        
        entry = {
            "id": entry_id,
            "timestamp": datetime.now().isoformat(),
            "drift_score": round(score, 3),
            "paranoia_multiplier": multiplier,
            "source_app": self._get_active_window(),
            "content_hash": self._hash_content(new_text),
            "content_snippet": new_text[:50].replace("\n", " ") + "..." if len(new_text) > 50 else new_text.replace("\n", " "),
            "old_length": len(old_text),
            "new_length": len(new_text),
            "tags": self._extract_tags(new_text),
            "status": "PENDING"
        }
        
        with self._lock:
            ledger = self._read_ledger()
            ledger["entries"].append(entry)
            ledger["last_modified"] = datetime.now().isoformat()
            ledger["session_stats"]["total_events"] += 1
            ledger["session_stats"]["pending"] += 1
            
            # Enforce max entries limit
            if len(ledger["entries"]) > MAX_ENTRIES:
                # Remove oldest PENDING entries
                pending = [e for e in ledger["entries"] if e["status"] == "PENDING"]
                if len(pending) > MAX_ENTRIES // 2:
                    # Remove oldest half of pending
                    to_remove = len(pending) - MAX_ENTRIES // 2
                    removed_ids = set(e["id"] for e in pending[:to_remove])
                    ledger["entries"] = [e for e in ledger["entries"] if e["id"] not in removed_ids]
                    ledger["session_stats"]["pending"] -= to_remove
            
            self._write_ledger(ledger)
        
        self.logger.info(f"[+] Silent Draft Logged: {entry_id} (Score: {score:.2f})")
        return entry_id
    
    def prune_stale_entries(self) -> int:
        """
        Remove entries older than STALE_HOURS.
        
        Returns:
            Number of entries removed
        """
        cutoff = datetime.now() - timedelta(hours=STALE_HOURS)
        removed = 0
        
        with self._lock:
            ledger = self._read_ledger()
            original_count = len(ledger["entries"])
            
            # Filter out stale entries
            ledger["entries"] = [
                e for e in ledger["entries"]
                if datetime.fromisoformat(e["timestamp"]) > cutoff
            ]
            
            removed = original_count - len(ledger["entries"])
            
            if removed > 0:
                # Update stats
                ledger["session_stats"]["pending"] = sum(
                    1 for e in ledger["entries"] if e["status"] == "PENDING"
                )
                ledger["last_modified"] = datetime.now().isoformat()
                self._write_ledger(ledger)
                self.logger.info(f"[*] Pruned {removed} stale entries from ledger")
        
        return removed
    
    def get_pending_entries(self) -> List[Dict[str, Any]]:
        """Get all pending entries for review."""
        with self._lock:
            ledger = self._read_ledger()
            return [e for e in ledger["entries"] if e["status"] == "PENDING"]
    
    def mark_reviewed(self, entry_id: str, approved: bool, notes: str = "") -> bool:
        """
        Mark an entry as reviewed.
        
        Args:
            entry_id: The entry ID to update
            approved: True if approved, False if rejected
            notes: Optional review notes
            
        Returns:
            True if entry was found and updated
        """
        with self._lock:
            ledger = self._read_ledger()
            
            for entry in ledger["entries"]:
                if entry["id"] == entry_id:
                    old_status = entry["status"]
                    entry["status"] = "APPROVED" if approved else "REJECTED"
                    entry["reviewed_at"] = datetime.now().isoformat()
                    entry["review_notes"] = notes
                    
                    # Update stats
                    if old_status == "PENDING":
                        ledger["session_stats"]["pending"] -= 1
                    if approved:
                        ledger["session_stats"]["approved"] += 1
                    else:
                        ledger["session_stats"]["rejected"] += 1
                    
                    ledger["last_modified"] = datetime.now().isoformat()
                    self._write_ledger(ledger)
                    return True
            
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current ledger statistics."""
        with self._lock:
            ledger = self._read_ledger()
            return {
                "total_entries": len(ledger["entries"]),
                **ledger["session_stats"],
                "last_modified": ledger.get("last_modified", "Never")
            }
    
    def clear_all(self):
        """Clear the entire ledger (for testing/reset)."""
        with self._lock:
            self._write_ledger(self._empty_ledger())
            self.logger.info("[!] Ledger cleared")


# Global instance
ledger = LedgerManager()
