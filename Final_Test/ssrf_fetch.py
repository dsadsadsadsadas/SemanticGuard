import requests
from fastapi import FastAPI
app = FastAPI()
@app.get('/fetch')
def fetch_url(url: str):
    # VULNERABLE: SSRF - fetching user-controlled URL directly
    return requests.get(url).text
