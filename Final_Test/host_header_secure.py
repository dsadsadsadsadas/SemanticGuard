from fastapi import FastAPI, Request
import os
app = FastAPI()
VALID_HOST = os.getenv('APP_DOMAIN', 'example.com')
@app.post('/reset_password')
def reset(request: Request, user_id: str):
    # SAFE: Using env configured host, not client Host header
    link = f"https://{VALID_HOST}/reset?token=123"
    send_email(user_id, link)
    return {"status": "sent"}
