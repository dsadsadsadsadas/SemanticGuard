# SSH Client
import paramiko

SSH_HOST = "prod-server.example.com"
SSH_USER = "root"
SSH_PASSWORD = "RootPassword123!"

def connect_to_server():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SSH_HOST, username=SSH_USER, password=SSH_PASSWORD)
    return client

def execute_remote_command(command):
    client = connect_to_server()
    stdin, stdout, stderr = client.exec_command(command)
    return stdout.read().decode()
