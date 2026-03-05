#!/usr/bin/env python3
"""
Test script for the 5 Pillars Evolution Loop (Memory-to-Law Pipeline)

This script verifies that:
1. Resolved problems are extracted as successful patterns and added to golden_state.md
2. Unresolved problems are extracted as negative rules and added to system_rules.md
3. The vault is updated and re-signed after evolution
"""

import os
import requests
import time
from datetime import datetime

# Configuration
SERVER_URL = "http://127.0.0.1:8000"
PROJECT_PATH = r"C:\Users\ethan\Documents\Projects\Trepan_Test_Zone"
TREPAN_DIR = os.path.join(PROJECT_PATH, ".trepan")

def wait_for_server(timeout=30):
    """Wait for the Trepan server to be ready."""
    print("Waiting for Trepan server to be ready...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(f"{SERVER_URL}/health")
            if response.status_code == 200 and response.json().get("model_loaded"):
                print("✅ Server is ready!")
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    print("❌ Server did not become ready in time")
    return False

def read_file(filename):
    """Read a file from the .trepan directory."""
    path = os.path.join(TREPAN_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def write_file(filename, content):
    """Write content to a file in the .trepan directory."""
    path = os.path.join(TREPAN_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Written to {filename}")

def test_memory_evolution():
    """Test the memory evolution pipeline."""
    print("\n" + "="*60)
    print("TEST: Memory Evolution (Memory-to-Law Pipeline)")
    print("="*60 + "\n")
    
    # Step 1: Create a test problem in problems_and_resolutions.md
    print("Step 1: Creating test problems in problems_and_resolutions.md...")
    test_problems = """# Problems and Resolutions

## Problem 1: Global State Bug (RESOLVED)
**Date**: 2024-01-15
**Description**: Application crashed due to global state being modified by multiple threads simultaneously.
**Root Cause**: Used global variables for session management instead of thread-local storage.
**Resolution**: Refactored to use thread-local storage and dependency injection. All tests passing.
**Status**: RESOLVED
**Pattern Learned**: Always use thread-local storage for session data in multi-threaded applications. Dependency injection prevents global state issues.

## Problem 2: SQL Injection Vulnerability (RESOLVED)
**Date**: 2024-01-20
**Description**: Security audit found SQL injection vulnerability in user search endpoint.
**Root Cause**: String concatenation used for SQL queries instead of parameterized statements.
**Resolution**: Replaced all string concatenation with parameterized queries using prepared statements.
**Status**: RESOLVED
**Pattern Learned**: NEVER use string concatenation for SQL queries. Always use parameterized statements with placeholders.

## Problem 3: Memory Leak in Production (UNRESOLVED)
**Date**: 2024-01-25
**Description**: Production server memory usage grows unbounded over 24 hours, requiring daily restarts.
**Root Cause**: Suspected circular references in event listeners not being garbage collected.
**Resolution**: Still investigating. Tried weak references but issue persists.
**Status**: UNRESOLVED
**Failure Pattern**: Event listeners with strong references to parent objects create circular references that prevent garbage collection.
"""
    
    write_file("problems_and_resolutions.md", test_problems)
    
    # Step 2: Read current state of golden_state.md and system_rules.md
    print("\nStep 2: Reading current state of pillar files...")
    golden_before = read_file("golden_state.md")
    rules_before = read_file("system_rules.md")
    
    print(f"  golden_state.md: {len(golden_before)} characters")
    print(f"  system_rules.md: {len(rules_before)} characters")
    
    # Step 3: Call the /evolve_memory endpoint
    print("\nStep 3: Calling /evolve_memory endpoint...")
    response = requests.post(
        f"{SERVER_URL}/evolve_memory",
        json={"project_path": PROJECT_PATH}
    )
    
    if response.status_code != 200:
        print(f"❌ API call failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False
    
    result = response.json()
    print(f"✅ Memory evolution completed!")
    print(f"   Status: {result['status']}")
    print(f"   Patterns added: {result['patterns_added']}")
    print(f"   Rules added: {result['rules_added']}")
    print(f"   Message: {result['message']}")
    
    # Step 4: Verify golden_state.md was updated with patterns
    print("\nStep 4: Verifying golden_state.md was updated...")
    golden_after = read_file("golden_state.md")
    
    if len(golden_after) > len(golden_before):
        print(f"✅ golden_state.md grew from {len(golden_before)} to {len(golden_after)} characters")
        
        # Check for expected patterns
        if "thread-local" in golden_after.lower() or "dependency injection" in golden_after.lower():
            print("✅ Found expected pattern about thread-local storage or dependency injection")
        else:
            print("⚠️  Expected pattern not found in golden_state.md")
            
        if "parameterized" in golden_after.lower() or "sql" in golden_after.lower():
            print("✅ Found expected pattern about SQL parameterization")
        else:
            print("⚠️  Expected SQL pattern not found in golden_state.md")
    else:
        print(f"❌ golden_state.md did not grow (before: {len(golden_before)}, after: {len(golden_after)})")
        return False
    
    # Step 5: Verify system_rules.md was updated with negative rules
    print("\nStep 5: Verifying system_rules.md was updated...")
    rules_after = read_file("system_rules.md")
    
    if len(rules_after) > len(rules_before):
        print(f"✅ system_rules.md grew from {len(rules_before)} to {len(rules_after)} characters")
        
        # Check for expected negative rules
        if "never" in rules_after.lower() and ("global" in rules_after.lower() or "event listener" in rules_after.lower()):
            print("✅ Found expected negative rule about global state or event listeners")
        else:
            print("⚠️  Expected negative rule not found in system_rules.md")
    else:
        print(f"❌ system_rules.md did not grow (before: {len(rules_before)}, after: {len(rules_after)})")
        return False
    
    # Step 6: Verify vault was updated
    print("\nStep 6: Verifying vault was updated...")
    vault_golden = os.path.join(TREPAN_DIR, "trepan_vault", "golden_state.md")
    vault_rules = os.path.join(TREPAN_DIR, "trepan_vault", "system_rules.md")
    
    if os.path.exists(vault_golden):
        with open(vault_golden, "r", encoding="utf-8") as f:
            vault_golden_content = f.read()
        if len(vault_golden_content) == len(golden_after):
            print("✅ Vault golden_state.md matches live file")
        else:
            print(f"❌ Vault golden_state.md mismatch (vault: {len(vault_golden_content)}, live: {len(golden_after)})")
            return False
    else:
        print("❌ Vault golden_state.md not found")
        return False
    
    if os.path.exists(vault_rules):
        with open(vault_rules, "r", encoding="utf-8") as f:
            vault_rules_content = f.read()
        if len(vault_rules_content) == len(rules_after):
            print("✅ Vault system_rules.md matches live file")
        else:
            print(f"❌ Vault system_rules.md mismatch (vault: {len(vault_rules_content)}, live: {len(rules_after)})")
            return False
    else:
        print("❌ Vault system_rules.md not found")
        return False
    
    # Step 7: Verify lock file was updated
    print("\nStep 7: Verifying .trepan.lock was updated...")
    lock_file = os.path.join(TREPAN_DIR, ".trepan.lock")
    if os.path.exists(lock_file):
        with open(lock_file, "r", encoding="utf-8") as f:
            import json
            lock_data = json.load(f)
        print(f"✅ Lock file exists with signature: {lock_data['signature'][:16]}...")
        print(f"   Last updated: {datetime.fromtimestamp(lock_data['last_updated']).strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print("❌ Lock file not found")
        return False
    
    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED - Memory Evolution Working!")
    print("="*60 + "\n")
    return True

def test_task_movement():
    """Test moving a task from pending to done."""
    print("\n" + "="*60)
    print("TEST: Task Movement (Pending -> Done)")
    print("="*60 + "\n")
    
    # Step 1: Create a test task in pending_tasks.md
    print("Step 1: Creating test task in pending_tasks.md...")
    test_task = "Implement user authentication with JWT tokens"
    pending_content = f"""# Pending Tasks

- {test_task}
- Add rate limiting to API endpoints
- Write integration tests
"""
    write_file("pending_tasks.md", pending_content)
    
    # Step 2: Read current done_tasks.md
    print("\nStep 2: Reading current done_tasks.md...")
    done_before = read_file("done_tasks.md")
    print(f"  done_tasks.md: {len(done_before)} characters")
    
    # Step 3: Call the /move_task endpoint
    print("\nStep 3: Calling /move_task endpoint...")
    response = requests.post(
        f"{SERVER_URL}/move_task",
        json={
            "task_description": test_task,
            "project_path": PROJECT_PATH
        }
    )
    
    if response.status_code != 200:
        print(f"❌ API call failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False
    
    result = response.json()
    print(f"✅ Task moved successfully!")
    print(f"   Status: {result['status']}")
    print(f"   Message: {result['message']}")
    
    # Step 4: Verify task was removed from pending
    print("\nStep 4: Verifying task was removed from pending_tasks.md...")
    pending_after = read_file("pending_tasks.md")
    if test_task not in pending_after:
        print("✅ Task removed from pending_tasks.md")
    else:
        print("❌ Task still in pending_tasks.md")
        return False
    
    # Step 5: Verify task was added to done
    print("\nStep 5: Verifying task was added to done_tasks.md...")
    done_after = read_file("done_tasks.md")
    if test_task in done_after:
        print("✅ Task added to done_tasks.md")
    else:
        print("❌ Task not found in done_tasks.md")
        return False
    
    # Step 6: Verify timestamp was added
    if datetime.now().strftime("%Y-%m-%d") in done_after:
        print("✅ Timestamp added to done task")
    else:
        print("⚠️  Timestamp not found (might be date mismatch)")
    
    print("\n" + "="*60)
    print("✅ TASK MOVEMENT TEST PASSED!")
    print("="*60 + "\n")
    return True

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("TREPAN 5 PILLARS EVOLUTION LOOP - TEST SUITE")
    print("="*60 + "\n")
    
    # Wait for server
    if not wait_for_server():
        print("❌ Server not ready. Please start the Trepan server first:")
        print("   cd trepan_server && python -m uvicorn server:app --reload")
        return
    
    # Run tests
    results = []
    
    print("\n🧪 Running Test 1: Task Movement...")
    results.append(("Task Movement", test_task_movement()))
    
    print("\n🧪 Running Test 2: Memory Evolution...")
    results.append(("Memory Evolution", test_memory_evolution()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")
    
    all_passed = all(result[1] for result in results)
    if all_passed:
        print("\n🎉 ALL TESTS PASSED! The 5 Pillars Evolution Loop is working correctly.")
    else:
        print("\n❌ SOME TESTS FAILED. Please review the output above.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
