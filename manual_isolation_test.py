#!/usr/bin/env python3
"""
Manual isolation test - assumes server is already running.
Run this after starting the server manually with: python start_server.py

IMPORTANT: Run this in the same conda environment as the server (trepan_beta_test)
"""

import requests
import json
import sys

SERVER_URL = "http://localhost:8001"

print(f"Python: {sys.executable}")
print(f"Requests version: {requests.__version__}")
print()
TEST_CODE = """const userEmail = req.body.email;
console.log(userEmail);"""

def test_audit():
    """Run a single audit test."""
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
    
    print("Sending request to /evaluate...")
    print(f"Timeout set to: 120 seconds")
    print(f"Waiting for response...")
    try:
        response = requests.post(f"{SERVER_URL}/evaluate", json=payload, timeout=120)
        if response.status_code == 200:
            data = response.json()
            raw_thoughts = data.get('raw_thoughts', '')
            verdict = data.get('verdict', 'UNKNOWN')
            char_count = len(raw_thoughts)
            
            print(f"\n✅ Generated {char_count} characters")
            print(f"✅ Verdict: {verdict}")
            print(f"\nFirst 200 chars of raw_thoughts:")
            print(raw_thoughts[:200])
            return char_count, verdict
        else:
            print(f"\n❌ HTTP {response.status_code}")
            print(response.text)
            return 0, f"HTTP_{response.status_code}"
    except requests.exceptions.Timeout:
        print("\n❌ Request timed out after 120 seconds")
        print("This means either:")
        print("  1. Ollama is hanging on this specific options configuration")
        print("  2. The model is taking extremely long to generate")
        print("  3. Check the server terminal for errors or where it's stuck")
        return 0, "TIMEOUT"
    except Exception as e:
        print(f"\n❌ Exception: {e}")
        return 0, f"ERROR"

if __name__ == "__main__":
    print("=" * 70)
    print("ISOLATION TEST - SINGLE RUN")
    print("=" * 70)
    print()
    
    # Check server health first
    try:
        resp = requests.get(f"{SERVER_URL}/health", timeout=2)
        if resp.status_code == 200:
            print("✅ Server is running\n")
        else:
            print("❌ Server returned non-200 status")
            exit(1)
    except:
        print("❌ Server is not running. Start it with: python start_server.py")
        exit(1)
    
    test_audit()
    print()
    print("=" * 70)
