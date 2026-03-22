#!/usr/bin/env python3
"""
Isolation diagnostic test script.
Tests each options configuration and reports results.
"""

import requests
import json

SERVER_URL = "http://localhost:8001"

TEST_CODE = """
const userEmail = req.body.email;
console.log(userEmail);
"""

def test_step(step_name):
    """Test a single step and return result."""
    payload = {
        "filename": "cool.js",
        "code_snippet": TEST_CODE,
        "pillars": {
            "system_rules": "Rule 1: No PII leaks",
            "golden_state": "",
            "done_tasks": "",
            "pending_tasks": "",
            "history_phases": ""
        },
        "project_path": "",
        "processor_mode": "GPU",
        "model_name": "deepseek-r1:latest"
    }
    
    try:
        response = requests.post(f"{SERVER_URL}/evaluate", json=payload, timeout=180)
        if response.status_code == 200:
            data = response.json()
            verdict = data.get('verdict', 'UNKNOWN')
            raw_len = len(data.get('raw_thoughts', ''))
            return f"Generated {raw_len} characters", verdict
        else:
            return f"HTTP {response.status_code}", "ERROR"
    except Exception as e:
        return f"Exception: {str(e)}", "ERROR"

if __name__ == "__main__":
    print("STEP 1 — Minimal options (temp=0.1, ctx=512, gpu=999)")
    gen1, verdict1 = test_step("step1")
    print(f"  {gen1}")
    print(f"  Verdict: {verdict1}\n")
