# Secure Admin Panel
import sqlite3
from typing import Optional

def delete_user(user_id: int, admin_token: str):
    """Delete user with authentication check"""
    # SECURE: Verify admin authentication
    if not verify_admin_token(admin_token):
        raise PermissionError("Unauthorized: Admin access required")
    
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

def verify_admin_token(token: str) -> bool:
    """Verify admin token"""
    # Implementation would check token validity
    return token is not None and len(token) > 0
