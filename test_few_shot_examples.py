import requests
import os
import json
import getpass
import asyncio
import sys
import time
from pathlib import Path

# Import TokenBucket for rate limiting
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'st'))
from token_bucket import TokenBucket

# Prompt for Groq API key at the start
print("="*60)
print("GROQ API KEY REQUIRED FOR POWER MODE")
print("="*60)
api_key = getpass.getpass("Enter your Groq API key: ").strip()

if not api_key:
    print("❌ No API key provided. Exiting.")
    exit(1)

print("✅ API key received. Starting tests...\n")

# Mode selection
print("="*60)
print("SELECT TEST MODE")
print("="*60)
print("[1] Audit Folder (C:\\Users\\ethan\\Desktop\\Trepan\\Final_Test)")
print("[2] Run Few-Shot Examples (5 specific test files)")
mode_choice = input("> ").strip()

SERVER_URL = "http://localhost:8001/evaluate_cloud"
FINAL_TEST_DIR = r"c:\Users\ethan\Desktop\Trepan\Final_Test"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"

# Detect TPM limits from API
print("\n" + "="*60)
print("DETECTING TPM LIMITS FROM GROQ API")
print("="*60)
try:
    test_response = requests.post(
        GROQ_ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 1
        },
        timeout=10
    )
    
    detected_tpm = None
    detected_rpm = None
    
    for key, value in test_response.headers.items():
        key_lower = key.lower()
        if 'ratelimit' in key_lower and 'request' in key_lower and 'limit' in key_lower:
            try:
                detected_rpm = int(value)
                print(f"✅ Detected RPM: {detected_rpm}")
            except ValueError:
                pass
        if 'ratelimit' in key_lower and 'token' in key_lower and 'limit' in key_lower:
            try:
                detected_tpm = int(value)
                print(f"✅ Detected TPM: {detected_tpm:,}")
            except ValueError:
                pass
    
    if not detected_tpm:
        detected_tpm = 30000  # Default for Llama 4 Scout
        detected_rpm = 30
        print(f"⚠️  Could not detect TPM from API, using defaults: {detected_tpm:,} TPM")
    
except Exception as e:
    print(f"⚠️  TPM detection failed: {e}")
    detected_tpm = 30000
    detected_rpm = 30
    print(f"Using defaults: {detected_tpm:,} TPM")

# Initialize TokenBucket with detected limits
rate_limiter = TokenBucket(max_rpm=detected_rpm, max_tpm=detected_tpm)
print(f"✅ TokenBucket initialized: {detected_tpm:,} TPM, {detected_rpm} RPM")
print(f"✅ Max file size: {rate_limiter.max_file_tokens:,} tokens (20% of TPM)")
print("="*60 + "\n")

# Detect server configuration
print("="*60)
print("DETECTING SERVER CONFIGURATION")
print("="*60)
try:
    health_response = requests.get("http://localhost:8001/health", timeout=5)
    if health_response.status_code == 200:
        health_data = health_response.json()
        detected_mode = health_data.get('engine_mode', 'unknown')
        server_version = health_data.get('version', 'unknown')
        print(f"✅ Server Version: {server_version}")
        print(f"✅ Server Mode: {detected_mode.upper()}")
        print(f"✅ Test Model: {MODEL_NAME}")
        print(f"✅ Endpoint: /evaluate_cloud (direct Groq, bypasses local Ollama)")
        print(f"✅ Confirmed: NOT using local llama3.1:8b model")
        if detected_mode.lower() == 'local':
            print("⚠️  WARNING: Server is in LOCAL mode but test uses CLOUD endpoint")
    else:
        print("⚠️  Could not detect server configuration")
except Exception as e:
    print(f"⚠️  Server health check failed: {e}")
print("="*60 + "\n")

# ── AUTOPSY MODE ────────────────────────────────────────────────────────────

async def run_autopsy(results, files_to_test):
    """Diagnose why files were incorrectly flagged as vulnerable (false positives)"""
    failed_results = [r for r in results if r.get('result_type') == 'FALSE_POSITIVE']
    
    if not failed_results:
        return
        
    for result in failed_results:
        filename = result['file']
        file_path = os.path.join(FINAL_TEST_DIR, filename)
        
        print(f"\n{'='*60}")
        print(f"[AUTOPSY] Analyzing false positive: {filename}")
        print(f"{'='*60}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            # Get the AI's reasoning from the result
            ai_reasoning = result.get('reasoning', 'No reasoning provided')
            violations = result.get('violations', [])
            
            system_prompt = (
                "You are the Chief Architect of the SemanticGuard Security Engine.\n"
                "Our engine just INCORRECTLY flagged a SAFE file as vulnerable (FALSE POSITIVE).\n"
                "Your job is to tell us WHY we flagged it incorrectly.\n\n"
                "The file is actually SAFE because:\n"
                "- Parameterized queries are used (? placeholders)\n"
                "- ORM operators like Op.like are parameterized internally\n"
                "- String() casting prevents NoSQL injection\n"
                "- jwt.verify() with algorithms list is secure\n"
                "- Database file paths like 'users.db' are config, not secrets\n\n"
                "Analyze the AI's reasoning and explain:\n"
                "1. What pattern did the AI incorrectly flag?\n"
                "2. Why is this pattern actually SAFE?\n"
                "3. What specific prompt rule should we add to prevent this false positive?\n\n"
                "Provide a 3-sentence explanation with ONE bullet point fix."
            )
            
            user_prompt = f"""File: {filename}

Code:
{code}

AI's Incorrect Reasoning:
{ai_reasoning}

Violations Flagged:
{json.dumps(violations, indent=2)}

Why did the AI incorrectly flag this safe code?"""
            
            print(f"[BRAIN] Analyzing AI reasoning...")
            
            response = await asyncio.to_thread(
                requests.post,
                GROQ_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 500
                },
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                diagnosis = data["choices"][0]["message"]["content"].strip()
                print(f"\n[DIAGNOSIS]")
                print(diagnosis)
                print()
            else:
                print(f"[ERROR] API Error during Autopsy: {response.status_code}")
                
        except Exception as e:
            print(f"[ERROR] Local Error during Autopsy: {str(e)}")

# ── MAIN TEST ───────────────────────────────────────────────────────────────

async def run_tests():
    """Main async test runner with rate limiting"""
    if mode_choice == "1":
        # Folder audit mode
        print("\n" + "="*60)
        print("FOLDER AUDIT MODE - SCANNING Final_Test/")
        print("="*60)
        
        # Scan all files in Final_Test directory
        files_to_test = []
        for file_path in Path(FINAL_TEST_DIR).glob("*"):
            if file_path.is_file() and file_path.suffix in ['.py', '.js', '.ts', '.java', '.go', '.rb', '.php']:
                files_to_test.append(file_path.name)
        
        print(f"Found {len(files_to_test)} files to audit:")
        for f in files_to_test:
            print(f"  - {f}")
        print()
    else:
        # Few-shot examples mode (default)
        print("\n" + "="*60)
        print("FEW-SHOT EXAMPLES MODE - 5 SPECIFIC TEST FILES")
        print("="*60)
        
        # The 5 files that should return {"findings": []} with few-shot examples
        files_to_test = [
            "database_secure.js",
            "hpp_vulnerable_secure.js",
            "nosql_injection_secure.js",
            "jwt_weak_secure.js",
            "admin_panel_secure.py"
        ]

    print("="*60)
    print("TESTING FILES - ALL SHOULD RETURN ACCEPT")
    print("="*60)

    results = []
    total_wait_time = 0.0
    
    # Pre-calculate token counts for all files
    file_tokens = {}
    for filename in files_to_test:
        path = os.path.join(FINAL_TEST_DIR, filename)
        with open(path, 'r', encoding='utf-8') as f:
            code = f.read()
        numbered_lines = [f"{i+1}: {line}" for i, line in enumerate(code.splitlines())]
        numbered_code = "\n".join(numbered_lines)
        estimated_tokens = len(numbered_code) // 4 + 500
        file_tokens[filename] = {
            "tokens": estimated_tokens,
            "numbered_code": numbered_code
        }
    
    # Concurrent execution with semaphore
    # Higher concurrency to compensate for server latency (server adds ~0.5-1s overhead per request)
    semaphore = asyncio.Semaphore(10)  # Allow 10 concurrent requests
    file_counter = {"count": 0}
    
    async def audit_with_semaphore(filename):
        async with semaphore:
            file_counter["count"] += 1
            idx = file_counter["count"]
            
            path = os.path.join(FINAL_TEST_DIR, filename)
            file_data = file_tokens[filename]
            numbered_code = file_data["numbered_code"]
            estimated_tokens = file_data["tokens"]
            
            # Task 2: Account for LLM output tokens (reserve 2000 tokens for response)
            total_tokens_to_consume = estimated_tokens + 2000
            
            # Check if file is too large
            if estimated_tokens > rate_limiter.max_file_tokens:
                print(f"\n[{idx}/{len(files_to_test)}] {filename}")
                print(f"  ⚠️  SKIPPED: File too large ({estimated_tokens:,} tokens > {rate_limiter.max_file_tokens:,} max)")
                return {
                    "file": filename,
                    "status": "SKIPPED",
                    "result_type": "SKIPPED"
                }
            
            # Wait for token availability
            wait_time = await rate_limiter.consume_with_wait(total_tokens_to_consume)
            
            # Determine expected result based on filename
            is_secure_file = "_secure" in filename
            expected_action = "ACCEPT" if is_secure_file else "REJECT"
            
            payload = {
                "filename": filename,
                "code_snippet": numbered_code,
                "project_path": r"c:\Users\ethan\Desktop\Trepan",
                "model_name": "meta-llama/llama-4-scout-17b-16e-instruct"
            }
            
            print(f"\n[{idx}/{len(files_to_test)}] {filename} [{estimated_tokens:,} tokens]")
            if wait_time > 0:
                print(f"  ⏳ Rate limit wait: {wait_time:.2f}s")
            print(f"  Expected: {expected_action}")
            
            # Track actual audit time (not including rate limit wait)
            audit_start = time.time()
            
            res = await asyncio.to_thread(
                requests.post,
                SERVER_URL, 
                json=payload, 
                timeout=60,
                headers={"Authorization": f"Bearer {api_key}"}
            )
            
            audit_time = time.time() - audit_start
            
            if res.status_code == 200:
                data = res.json()
                action = data.get("action")
                violations = data.get("violations", [])
                findings = data.get("findings", [])
                
                # Get actual token usage from API response
                tokens_used = data.get("usage", {}).get("total_tokens", estimated_tokens)
                if not tokens_used:
                    tokens_used = data.get("tokens_used", estimated_tokens)
                
                # Refund difference if actual is lower than estimate
                rate_limiter.refund(total_tokens_to_consume, tokens_used)
                
                # Use violations if findings is empty
                actual_findings = violations if not findings else findings
                
                # Determine if result is correct
                if is_secure_file:
                    if action == "ACCEPT" and len(actual_findings) == 0:
                        status = "✅ PASS (Correctly identified as secure)"
                        result_type = "TRUE_NEGATIVE"
                    else:
                        status = "❌ FAIL - FALSE POSITIVE (Secure file flagged as vulnerable)"
                        result_type = "FALSE_POSITIVE"
                else:
                    if action == "REJECT" and len(actual_findings) > 0:
                        status = "✅ PASS (Correctly identified as vulnerable)"
                        result_type = "TRUE_POSITIVE"
                    else:
                        status = "❌ FAIL - FALSE NEGATIVE (Vulnerable file flagged as secure)"
                        result_type = "FALSE_NEGATIVE"
                
                result = {
                    "file": filename,
                    "status": status,
                    "result_type": result_type,
                    "action": action,
                    "expected": expected_action,
                    "findings_count": len(actual_findings),
                    "reasoning": data.get("reasoning", ""),
                    "violations": actual_findings,
                    "wait_time": wait_time,
                    "audit_time": audit_time
                }
                
                print(f"  Result: {action} - {status}")
                print(f"  ⏱️  Audit time: {audit_time:.2f}s")
                print(f"  Violations: {len(violations)}, Findings: {len(findings)}")
                if actual_findings:
                    for f in actual_findings:
                        vuln_type = f.get('vulnerability_type', 'UNKNOWN_VULNERABILITY')
                        severity = f.get('severity', 'UNKNOWN_SEVERITY')
                        reasoning = f.get('reasoning', f.get('description', f.get('violation', 'NO_REASONING')))
                        print(f"\n    [VULNERABILITY TYPE]: {vuln_type}")
                        print(f"    [SEVERITY]: {severity}")
                        print(f"    [AI REASONING]: {reasoning}")
                        print()
                
                return result
            else:
                print(f"  ❌ ERROR: {res.status_code}")
                return {"file": filename, "status": "ERROR", "result_type": "ERROR", "wait_time": wait_time, "audit_time": audit_time}
    
    # Launch all files concurrently
    audit_start_time = time.time()
    tasks = [audit_with_semaphore(filename) for filename in files_to_test]
    results = await asyncio.gather(*tasks)
    total_audit_time = time.time() - audit_start_time
    
    # Calculate total wait time
    total_wait_time = sum(r.get("wait_time", 0) for r in results if r.get("wait_time"))

    # Print final results
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)

    # Categorize results
    true_positives = [r for r in results if r.get('result_type') == 'TRUE_POSITIVE']
    true_negatives = [r for r in results if r.get('result_type') == 'TRUE_NEGATIVE']
    false_positives = [r for r in results if r.get('result_type') == 'FALSE_POSITIVE']
    false_negatives = [r for r in results if r.get('result_type') == 'FALSE_NEGATIVE']
    errors = [r for r in results if r.get('result_type') == 'ERROR']

    for r in results:
        print(f"{r['file']}: {r['status']}")

    # Summary statistics
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    print(f"✅ TRUE POSITIVES (Vulnerable files correctly flagged): {len(true_positives)}")
    print(f"✅ TRUE NEGATIVES (Secure files correctly passed): {len(true_negatives)}")
    print(f"❌ FALSE POSITIVES (Secure files incorrectly flagged): {len(false_positives)}")
    print(f"❌ FALSE NEGATIVES (Vulnerable files incorrectly passed): {len(false_negatives)}")
    if errors:
        print(f"⚠️  ERRORS: {len(errors)}")

    total_correct = len(true_positives) + len(true_negatives)
    total_tests = len(results) - len(errors)
    accuracy = (total_correct / total_tests * 100) if total_tests > 0 else 0
    
    # Calculate timing statistics
    total_audit_time_sum = sum(r.get("audit_time", 0) for r in results if r.get("audit_time"))
    avg_audit_time = (total_audit_time_sum / total_tests) if total_tests > 0 else 0

    print(f"\n📊 ACCURACY: {total_correct}/{total_tests} ({accuracy:.1f}%)")
    print(f"⏱️  TOTAL WAIT TIME: {total_wait_time:.2f}s")
    print(f"⏱️  TOTAL AUDIT TIME: {total_audit_time:.2f}s (wall clock)")
    print(f"⏱️  TOTAL API TIME: {total_audit_time_sum:.2f}s (sum of all file audit times)")
    print(f"⚡ AVG AUDIT TIME PER FILE: {avg_audit_time:.2f}s")

    # Detailed false positive analysis
    if false_positives:
        print("\n" + "="*60)
        print("⚠️  FALSE POSITIVE ANALYSIS")
        print("="*60)
        for fp in false_positives:
            print(f"\n❌ {fp['file']} (Secure file incorrectly flagged)")
            if fp.get('violations'):
                for v in fp['violations']:
                    print(f"   Reason: {v.get('reasoning', v.get('description', 'No reason'))[:200]}")

    # Detailed false negative analysis
    if false_negatives:
        print("\n" + "="*60)
        print("⚠️  FALSE NEGATIVE ANALYSIS")
        print("="*60)
        for fn in false_negatives:
            print(f"\n❌ {fn['file']} (Vulnerable file incorrectly passed)")
            print(f"   AI should have detected vulnerabilities but returned ACCEPT")

    # Run Autopsy Mode for false positives only
    if false_positives:
        print("\n" + "="*60)
        print("AUTOPSY MODE - ANALYZING FALSE POSITIVES")
        print("="*60)
        await run_autopsy(false_positives, files_to_test)

# Run the async test
asyncio.run(run_tests())

