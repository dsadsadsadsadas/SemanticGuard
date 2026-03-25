from fastapi import FastAPI, Depends, HTTPException
import sqlite3
app = FastAPI()
def get_current_user_id(): return 5 # Mock auth
@app.get('/user/{user_id}')
def get_profile(user_id: int, current_user: int = Depends(get_current_user_id)):
    if user_id != current_user: raise HTTPException(status_code=403)
    conn = sqlite3.connect('db.sqlite')
    return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
