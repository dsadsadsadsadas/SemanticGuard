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
