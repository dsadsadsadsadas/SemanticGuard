from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
import urllib.parse
app = FastAPI()
@app.get('/login')
def login(request: Request, next_url: str):
    # SAFE: Open Redirect defense by validating path vs host
    parsed = urllib.parse.urlparse(next_url)
    if parsed.netloc and parsed.netloc != 'example.com':
        raise HTTPException(400, 'Invalid redirect')
    return RedirectResponse(url=next_url)
