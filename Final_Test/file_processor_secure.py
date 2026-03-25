# Secure File Processing
import subprocess
from pathlib import Path

def process_file(filename: str):
    """Process file securely without shell injection"""
    filepath = Path(filename)
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filename}")
    
    # SECURE: No shell=True, arguments as list
    result = subprocess.run(
        ['grep', 'error', str(filepath)],
        capture_output=True,
        text=True,
        check=False
    )
    return result.stdout

def compress_file(filepath: str):
    """Compress file securely"""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    # SECURE: Arguments as list, no shell
    subprocess.run(
        ['tar', '-czf', f'{filepath}.tar.gz', filepath],
        check=True
    )
