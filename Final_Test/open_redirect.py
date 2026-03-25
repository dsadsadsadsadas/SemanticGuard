from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
app = FastAPI()
@app.get('/login')
def login(request: Request, next_url: str):
    # VULNERABLE: Open Redirect based on user input
    return RedirectResponse(url=next_url)
