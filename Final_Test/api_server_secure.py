# Secure API Server (FastAPI)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr

app = FastAPI()

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    age: int

@app.post('/api/users')
async def create_user(user: UserCreate):
    """Create user with Pydantic validation"""
    # SECURE: Pydantic validates all inputs
    return {"status": "created", "username": user.username}

@app.get('/health')
async def health_check():
    return {"status": "healthy"}
