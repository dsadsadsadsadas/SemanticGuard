# Groq API Client
GROQ_API_KEY = "gsk_1234567890abcdefghijklmnopqrstuvwxyz"

def call_groq_api(prompt):
    import requests
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    response = requests.post("https://api.groq.com/v1/chat", 
        headers=headers, json={"prompt": prompt})
    return response.json()
