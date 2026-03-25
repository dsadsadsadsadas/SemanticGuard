# Backup Manager
import subprocess

def backup_database(db_name):
    # VULNERABLE: Command Injection with shell=True
    subprocess.run(f"pg_dump {db_name} > backup.sql", shell=True)
    
def restore_database(backup_file):
    # VULNERABLE: Command Injection
    subprocess.run(f"psql < {backup_file}", shell=True)
