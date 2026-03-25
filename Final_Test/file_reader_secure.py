# Secure File Reader Service
import os
from pathlib import Path

ALLOWED_DIR = Path('/var/app/user_files').resolve()

def read_user_file(filename: str) -> str:
    """Read file with path traversal protection"""
    requested_path = (ALLOWED_DIR / filename).resolve()
    
    # SECURE: Validate path is within allowed directory
    if not str(requested_path).startswith(str(ALLOWED_DIR)):
        raise ValueError("Path traversal attempt detected")
    
    if not requested_path.exists():
        raise FileNotFoundError(f"File not found: {filename}")
    
    with requested_path.open('r') as f:
        return f.read()

def download_file(file_path: str) -> bytes:
    """Download file with validation"""
    requested_path = (ALLOWED_DIR / file_path).resolve()
    
    # SECURE: Path validation
    if not str(requested_path).startswith(str(ALLOWED_DIR)):
        raise ValueError("Invalid file path")
    
    with requested_path.open('rb') as f:
        return f.read()
