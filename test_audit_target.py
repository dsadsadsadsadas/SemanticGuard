import os
import sqlite3

# VULNERABILITY 1: Hardcoded Secret
AWS_ACCESS_KEY = "AKIA1234567890FAKEKEY" 
DB_PASSWORD = "super_secret_password_123"

def get_user_data(username):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # VULNERABILITY 2: SQL Injection (Unsafe String Concatenation)
    # The auditor should flag this as dangerous.
    query = "SELECT * FROM users WHERE name = '" + username + "'"
    cursor.execute(query)
    
    return cursor.fetchall()

def ping_server(ip_address):
    # VULNERABILITY 3: Command Injection
    # Passing untrusted input directly to the shell
    command = "ping -c 1 " + ip_address
    os.system(command)

if __name__ == "__main__":
    print("Test script loaded.")