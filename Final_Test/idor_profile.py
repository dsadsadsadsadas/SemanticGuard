from fastapi import FastAPI
import sqlite3
app = FastAPI()
@app.get('/user/{user_id}')
def get_profile(user_id: int):
    # VULNERABLE: IDOR - no authorization check that requester == user_id
    conn = sqlite3.connect('db.sqlite')
    return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
