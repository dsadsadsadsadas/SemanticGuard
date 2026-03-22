"""
Live Test 2: Layer 2 should catch this
Expected: [LAYER 2 — FOCUSED ANALYSIS]
Layer 1 won't catch this (no hardcoded secrets, no shell=True, etc.)
Layer 2 should detect: name from req.body reaches print() without sanitization
"""

def handle_request(req):
    name = req.body['name']
    print(name)
    return "OK"
