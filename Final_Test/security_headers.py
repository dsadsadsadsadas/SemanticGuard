from fastapi import FastAPI
from fastapi.responses import HTMLResponse
app = FastAPI()
@app.get('/')
def index():
    # VULNERABLE: Serving HTML without X-Frame-Options (Clickjacking)
    return HTMLResponse("<html><body>Sensitive Portal</body></html>")
