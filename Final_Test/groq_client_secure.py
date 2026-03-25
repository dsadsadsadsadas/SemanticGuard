# Secure Groq API Client
import os
import httpx

async def call_groq_api(prompt: str) -> dict:
    """Call Groq API with key from environment"""
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in environment")
    
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.groq.com/v1/chat",
            headers=headers,
            json={"prompt": prompt}
        )
        response.raise_for_status()
        return response.json()
