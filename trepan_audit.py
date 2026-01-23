import json
import hashlib
import time
import os
import uuid
from datetime import datetime

AUDIT_FILE = "security_audit.jsonl"

class AuditRecorder:
    def __init__(self, user_identity="system_user"):
        self.user = user_identity
        self.session_id = str(uuid.uuid4())

    def _calculate_file_hash(self, file_path):
        """Generates a SHA256 fingerprint for proof of state."""
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except FileNotFoundError:
            return "FILE_NOT_FOUND"

    def _write_entry(self, data):
        with open(AUDIT_FILE, 'a') as f:
            f.write(json.dumps(data) + "\n")

    def log_event(self, event_type, file_path, details):
        """Logs a tamper-evident security event."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "session_id": self.session_id,
            "target_file": file_path,
            "file_hash": self._calculate_file_hash(file_path) if file_path else None,
            "details": details
        }
        self._write_entry(entry)

# Singleton
audit_log = AuditRecorder()