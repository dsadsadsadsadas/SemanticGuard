# Golden State (The Whitelist)

## 1. Mandatory Tech Stack & Versions
You MUST strictly use the following libraries. Do NOT introduce alternatives.
* **Backend Framework:** FastAPI (v0.100+)
* **Validation:** Pydantic (v2.0+)
* **Authentication:** python-jose (JWT generation only)

## 2. Approved Structural Boilerplate
When generating new files, you MUST follow this exact structure.

### [Example: API Endpoint Whitelist Structure]
```python
from fastapi import APIRouter, Depends
# ONLY use approved dependencies here

router = APIRouter()

@router.post("/endpoint")
async def standard_route(data: dict):
    # Mandatory flow: Validate -> Process -> Return
    return {"status": "success"}
```


# Project: SecureVault API (Implementation Plan)

## CORE ARCHITECTURE
- Framework: MUST use **FastAPI**. (Do not use Flask or Django).
- Data Validation: MUST use **Pydantic v2** models for all inputs.
- Async Policy: All I/O operations (Database/Network) MUST be **async/await**.

## APPROVED STACK
- Database: **PostgreSQL** via SQLAlchemy 2.0.
- Networking: Use **httpx** for external API calls. (STRICTLY PROHIBITED: `requests` library).
- Auth: JWT tokens using **HS256** algorithm only. 

## SECURITY PILLARS
- No raw SQL strings; use the ORM.
- Secret keys must be loaded via `os.getenv`, never hardcoded.