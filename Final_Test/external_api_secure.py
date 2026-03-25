# Secure External API Client (httpx)
import httpx
from typing import Dict, Any

async def fetch_user_data(user_id: int) -> Dict[str, Any]:
    """Fetch user data using httpx (approved library)"""
    # SECURE: Using httpx as per golden state
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.example.com/users/{user_id}",
            timeout=10.0
        )
        response.raise_for_status()
        return response.json()

async def post_analytics(data: Dict[str, Any]):
    """Post analytics using httpx"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://analytics.example.com/events",
            json=data,
            timeout=5.0
        )
        response.raise_for_status()
