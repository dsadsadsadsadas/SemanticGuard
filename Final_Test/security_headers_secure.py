from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
app = FastAPI()
@app.get('/')
def index(response: Response):
    # SAFE: Clickjacking defense applied
    response.headers['X-Frame-Options'] = 'DENY'
    return HTMLResponse("<html><body>Sensitive Portal</body></html>")
