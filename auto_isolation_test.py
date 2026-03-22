#!/usr/bin/env python3
"""
Automated isolation diagnostic - runs all 4 steps without manual intervention.
"""

import requests
import json
import time
import subprocess
import sys
import os

SERVER_URL = "http://localhost:8001"
TEST_CODE = """const userEmail = req.body.email;
console.log(userEmail);"""

def wait_for_server(max_wait=30):
    """Wait for server to be ready."""
    for i in range(max_wait):
        try:
            resp = requests.get(f"{SERVER_URL}/health", timeout=2)
            if resp.status_code == 200:
                print(f"   Server ready after {i+1}s")
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
        print("   Sending request to /evaluate...")
        response = requests.post(f"{SERVER_URL}/evaluate", json=payload, timeout=60)
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
        return 0, f"ERROR: {str(e)[:30]}"

def update_options(step_name, options_code):
    """Update model_loader.py with new options."""
    with open("trepan_server/model_loader.py", "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Find the options block
    start_idx = -1
    end_idx = -1
    
    for i, line in enumerate(lines):
        if "# STEP" in line or "options = {" in line:
            start_idx = i
        if start_idx != -1 and line.strip() == "}" and i > start_idx:
            end_idx = i + 1
            break
    
    if start_idx == -1 or end_idx == -1:
        print(f"   ERROR: Could not find options block")
        return False
    
    # Replace the block
    new_lines = lines[:start_idx] + [options_code] + lines[end_idx:]
    
    with open("trepan_server/model_loader.py", "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    print(f"   Updated options to {step_name}")
    return True

def kill_server():
    """Kill any running Python server processes."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/FI", "WINDOWTITLE eq Trepan*"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    else:
        subprocess.run(["pkill", "-f", "start_server.py"], 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

def start_server():
    """Start the server in background."""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    
    proc = subprocess.Popen(
        [sys.executable, "start_server.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs
    )
    return proc

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

print("=" * 70)
print("ISOLATION DIAGNOSTIC — AUTOMATED RUN")
print("=" * 70)
print()

results = []

for step_name, options_code in steps:
    print(f"{step_name}")
    print("-" * 70)
    
    # Update options
    if not update_options(step_name, options_code):
        results.append((step_name, 0, "UPDATE_FAILED"))
        continue
    
    # Kill any existing server
    kill_server()
    
    # Start server
    print("   Starting server...")
    proc = start_server()
    
    # Wait for server
    if not wait_for_server():
        print("   ERROR: Server did not start in time")
        results.append((step_name, 0, "SERVER_START_FAILED"))
        proc.kill()
        continue
    
    # Run test
    char_count, verdict = test_audit()
    print(f"   Generated {char_count} characters")
    print(f"   Verdict: {verdict}")
    print()
    
    results.append((step_name, char_count, verdict))
    
    # Kill server
    proc.kill()
    time.sleep(2)
    
    # Stop if we hit 0 characters
    if char_count == 0:
        print(f"⚠️  STOPPED AT {step_name} — Generated 0 characters")
        print(f"⚠️  CULPRIT IDENTIFIED: The option added in {step_name}")
        print()
        break

print("=" * 70)
print("RESULTS SUMMARY")
print("=" * 70)
for step, chars, verdict in results:
    status = "✅ PASS" if chars > 0 else "❌ FAIL"
    print(f"{status} {step}: Generated {chars} characters, Verdict: {verdict}")

print()
print("=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
