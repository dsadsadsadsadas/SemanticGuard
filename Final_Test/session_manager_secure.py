# Secure Session Manager
import json
from pathlib import Path
from typing import Dict, Any

def save_session(session_data: Dict[str, Any]):
    """Save session using JSON (not pickle)"""
    # SECURE: JSON is safe, pickle is not
    with Path('session.json').open('w') as f:
        json.dump(session_data, f)

def load_session() -> Dict[str, Any]:
    """Load session safely"""
    with Path('session.json').open('r') as f:
        return json.load(f)
