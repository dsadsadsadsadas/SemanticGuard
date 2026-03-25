# Authentication Service
import jwt

JWT_SECRET = "my-super-secret-key-12345"

def create_token(user_id):
    payload = {"user_id": user_id}
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token

def verify_token(token):
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
