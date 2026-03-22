#!/usr/bin/env python3
"""
Complete isolation diagnostic - runs all 4 steps automatically.
"""

import requests
import json
import time
import subprocess
import sys

SERVER_URL = "http://localhost:8001"

TEST_CODE = """const userEmail = req.body.email;
console.log(userEmail);"""

def wait_for_server():
    """Wait for server to be ready."""
    for _ in range(30):
        try:
            resp = requests.get(f"{SERVER_URL}/health", timeout=2)
            if resp.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False

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
    
    try:
        response = requests.post(f"{SERVER_URL}/evaluate", json=payload, timeout=45)
        if response.status_code == 200:
            data = response.json()
            raw_thoughts = data.get('raw_thoughts', '')
            verdict = data.get('verdict', 'UNKNOWN')
            return len(raw_thoughts), verdict
        else:
            return 0, f"HTTP_{response.status_code}"
    except requests.exceptions.Timeout:
        return 0, "TIMEOUT"
    except Exception as e:
        return 0, f"ERROR_{str(e)[:20]}"

def update_options(options_code):
    """Update model_loader.py with new options."""
    with open("trepan_server/model_loader.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Find and replace options block
    start_marker = "    # STEP"
    end_marker = "    }\n    \n    payload"
    
    start_idx = content.find(start_marker)
    if start_idx == -1:
        start_marker = "    options = {"
        start_idx = content.find(start_marker)
    
    end_idx = content.find(end_marker, start_idx)
    
    if start_idx != -1 and end_idx != -1:
        new_content = content[:start_idx] + options_code + content[end_idx:]
        with open("trepan_server/model_loader.py", "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    return False

# Test configurations
steps = [
    ("STEP 1", """    # STEP 1 — Minimal options
    options = {
        "temperature": 0.1,
        "num_ctx": 512,
        "num_gpu": 999,
    }
    
"""),
    ("STEP 2", """    # STEP 2 — Add num_predict
    options = {
        "temperature": 0.1,
        "num_ctx": 512,
        "num_gpu": 999,
        "num_predict": 800,
    }
    
"""),
    ("STEP 3", """    # STEP 3 — Add num_ctx: 2048
    options = {
        "temperature": 0.1,
        "num_ctx": 2048,
        "num_gpu": 999,
        "num_predict": 800,
    }
    
"""),
    ("STEP 4", """    # STEP 4 — Add num_thread: 8
    options = {
        "temperature": 0.1,
        "num_ctx": 2048,
        "num_gpu": 999,
        "num_predict": 800,
        "num_thread": 8,
    }
    
"""),
]

print("="*60)
print("ISOLATION DIAGNOSTIC TEST")
print("="*60)

results = []

for step_name, options_code in steps:
    print(f"\n{step_name}")
    print("-" * 40)
    
    # Update options
    if not update_options(options_code):
        print("ERROR: Could not update options")
        results.append((step_name, 0, "UPDATE_FAILED"))
        continue
    
    # Restart server (kill any existing)
    subprocess.run(["taskkill", "//F", "//IM", "python.exe"], 
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    
    # Start server
    proc = subprocess.Popen(
        ["python", "start_server.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )
    
    # Wait for server
    if not wait_for_server():
        print("ERROR: Server did not start")
        results.append((step_name, 0, "SERVER_START_FAILED"))
        proc.kill()
        continue
    
    # Run test
    char_count, verdict = test_audit()
    print(f"Generated {char_count} characters")
    print(f"Verdict: {verdict}")
    
    results.append((step_name, char_count, verdict))
    
    # Kill server
    proc.kill()
    time.sleep(2)
    
    # Stop if we hit 0 characters
    if char_count == 0:
        print(f"\n⚠️  STOPPED AT {step_name} - Generated 0 characters")
        break

print("\n" + "="*60)
print("RESULTS SUMMARY")
print("="*60)
for step, chars, verdict in results:
    print(f"{step}: Generated {chars} characters, Verdict: {verdict}")

print("\n" + "="*60)
