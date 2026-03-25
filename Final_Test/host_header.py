from fastapi import FastAPI, Request
app = FastAPI()
@app.post('/reset_password')
def reset(request: Request, user_id: str):
    # VULNERABLE: Host Header Injection generating password reset links
    host = request.headers.get('Host')
    link = f"https://{host}/reset?token=123"
    send_email(user_id, link)
    return {"status": "sent"}
