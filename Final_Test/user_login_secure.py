# Secure User Authentication
import sqlite3
from typing import Optional

def authenticate_user(username: str, password: str) -> bool:
    """Authenticate user with parameterized query"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # SECURE: Parameterized query prevents SQL injection
    query = "SELECT * FROM users WHERE username=? AND password=?"
    cursor.execute(query, (username, password))
    user = cursor.fetchone()
    conn.close()
    
    return user is not None
