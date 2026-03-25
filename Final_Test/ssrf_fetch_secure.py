import requests
from fastapi import FastAPI, HTTPException
from urllib.parse import urlparse
app = FastAPI()
ALLOWED_DOMAINS = ['api.example.com']
@app.get('/fetch')
def fetch_url(url: str):
    if urlparse(url).netloc not in ALLOWED_DOMAINS:
        raise HTTPException(403, 'Forbidden domain')
    return requests.get(url).text
