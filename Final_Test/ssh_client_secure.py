# Secure SSH Client
import os
import paramiko
from pathlib import Path

def get_ssh_config():
    """Get SSH configuration from environment"""
    return {
        'host': os.getenv('SSH_HOST'),
        'user': os.getenv('SSH_USER'),
        'key_path': os.getenv('SSH_KEY_PATH')
    }

def connect_to_server():
    """Connect using key-based authentication"""
    config = get_ssh_config()
    
    if not all(config.values()):
        raise ValueError("SSH configuration incomplete")
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    # SECURE: Key-based authentication, no password
    key_path = Path(config['key_path'])
    private_key = paramiko.RSAKey.from_private_key_file(str(key_path))
    
    client.connect(
        config['host'],
        username=config['user'],
        pkey=private_key
    )
    return client

def execute_remote_command(command: str) -> str:
    """Execute command with validation"""
    # Validate command (whitelist approach)
    allowed_commands = ['ls', 'pwd', 'whoami', 'date']
    if command.split()[0] not in allowed_commands:
        raise ValueError(f"Command not allowed: {command}")
    
    client = connect_to_server()
    stdin, stdout, stderr = client.exec_command(command)
    return stdout.read().decode()
