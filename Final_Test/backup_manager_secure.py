# Secure Backup Manager
import subprocess
from pathlib import Path

def backup_database(db_name: str, output_file: str):
    """Backup database securely"""
    # Validate database name (alphanumeric only)
    if not db_name.isalnum():
        raise ValueError("Invalid database name")
    
    output_path = Path(output_file)
    
    # SECURE: No shell=True, arguments as list
    with output_path.open('w') as f:
        subprocess.run(
            ['pg_dump', db_name],
            stdout=f,
            check=True
        )

def restore_database(backup_file: str):
    """Restore database securely"""
    backup_path = Path(backup_file)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_file}")
    
    # SECURE: No shell, stdin from file
    with backup_path.open('r') as f:
        subprocess.run(['psql'], stdin=f, check=True)
