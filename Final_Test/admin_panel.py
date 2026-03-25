# Admin Panel
def delete_user(user_id):
    # VULNERABLE: No authentication check
    import sqlite3
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()

def view_all_passwords():
    # VULNERABLE: No authorization
    import sqlite3
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    return cursor.execute("SELECT username, password FROM users").fetchall()
