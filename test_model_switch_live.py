#!/usr/bin/env python3
"""
Live test for model switching with duplicate system prompt fix.
Tests both Llama 3.1:8b (Fast Mode) and DeepSeek-R1:7b (Smart Mode).
"""

import requests
import json
import time

SERVER_URL = "http://localhost:8001"

# Test code with PII violation
TEST_CODE = """
user_email = req.body['email']
print(user_email)
"""

def test_model(model_name: str, mode_label: str):
    """Test a single model and return timing + RAW THOUGHTS."""
    print(f"\n{'='*60}")
    print(f"Testing {mode_label} ({model_name})")
    print(f"{'='*60}")
    
    payload = {
        "filename": "test.py",
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
        "model_name": model_name
    }
    
    start = time.time()
    response = requests.post(f"{SERVER_URL}/evaluate", json=payload, timeout=180)
    elapsed = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n⏱️  Audit Time: {elapsed:.2f}s")
        print(f"\n📊 Verdict: {data.get('verdict', 'UNKNOWN')}")
        print(f"\n💭 RAW THOUGHTS (first 500 chars):")
        print(data.get('raw_thoughts', 'EMPTY')[:500])
        return elapsed, data
    else:
        print(f"❌ Request failed: {response.status_code}")
        print(response.text)
        return None, None

if __name__ == "__main__":
    print("🧪 LIVE MODEL SWITCH TEST — Duplicate System Prompt Fix Validation")
    
    # Test 1: Fast Mode (Llama 3.1:8b)
    llama_time, llama_data = test_model("llama3.1:8b", "⚡ Fast Mode")
    
    # Test 2: Smart Mode (DeepSeek-R1:7b)
    deepseek_time, deepseek_data = test_model("deepseek-r1:7b", "🧠 Smart Mode")
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    if llama_time:
        print(f"⚡ Fast Mode (Llama):    {llama_time:.2f}s — Verdict: {llama_data.get('verdict')}")
    if deepseek_time:
        print(f"🧠 Smart Mode (DeepSeek): {deepseek_time:.2f}s — Verdict: {deepseek_data.get('verdict')}")
