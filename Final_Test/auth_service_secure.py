# Secure Authentication Service
import os
import jwt
from datetime import datetime, timedelta

def get_jwt_secret() -> str:
    """Get JWT secret from environment"""
    secret = os.getenv('JWT_SECRET')
    if not secret:
        raise ValueError("JWT_SECRET not found in environment")
    return secret

def create_token(user_id: int) -> str:
    """Create JWT token"""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")

def verify_token(token: str) -> dict:
    """Verify JWT token"""
    return jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
