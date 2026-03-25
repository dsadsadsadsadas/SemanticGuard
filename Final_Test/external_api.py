# External API Client (CONTEXT DRIFT: Using requests)
import requests

def fetch_user_data(user_id):
    # CONTEXT DRIFT: Should use httpx, not requests
    response = requests.get(f"https://api.example.com/users/{user_id}")
    return response.json()

def post_analytics(data):
    # CONTEXT DRIFT: requests library forbidden
    requests.post("https://analytics.example.com/events", json=data)
