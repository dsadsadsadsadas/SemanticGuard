"""
Live Test 1: Layer 1 should catch this
Expected: [LAYER 1 — NO MODEL CALL]
"""

# Hardcoded API key - Layer 1 should catch this instantly
api_key = "sk-abc123secretkey999"

def connect_to_api():
    return f"Connecting with {api_key}"
