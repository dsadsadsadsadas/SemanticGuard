import requests
import os
import json

SERVER_URL = "http://localhost:8001/evaluate"
FINAL_TEST_DIR = r"c:\Users\ethan\Desktop\Trepan\Final_Test"

files_to_test = [
    ("api_server.py", "REJECT", "debug=True"),
    ("database_secure.js", "ACCEPT", "Findings should be empty"),
    ("render_template.py", "REJECT", "XSS - no escaping")
]

results = []

for filename, expected_action, description in files_to_test:
    path = os.path.join(FINAL_TEST_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # Update payload to match server schema
    payload = {
        "filename": filename,
        "code_snippet": code,
        "pillars": {
            "system_rules": "", # Server will load from disk if project_path is provided? No, it expects it in the request usually for the extension.
            "golden_state": "",
            "done_tasks": "",
            "pending_tasks": "",
            "history_phases": "",
            "problems_and_resolutions": ""
        },
        "project_path": r"c:\Users\ethan\Desktop\Trepan",
        "processor_mode": "GPU",
        "model_name": "llama3.1:8b", # Explicitly use the target model
        "power_mode": False # We want full audit
    }
    
    print(f"Testing {filename} ({description})...")
    res = requests.post(SERVER_URL, json=payload)
    if res.status_code == 200:
        data = res.json()
        action = data.get("action")
        findings = data.get("findings", [])
        
        status = "PASS" if action == expected_action else "FAIL"
        results.append({
            "file": filename,
            "status": status,
            "action": action,
            "expected": expected_action,
            "findings_count": len(findings)
        })
        print(f"  Result: {action} (Expected: {expected_action}) - {status}")
        if findings:
            for f in findings:
                print(f"    - {f.get('rule_id')}: {f.get('reasoning')[:100]}...")
    else:
        print(f"  Error: {res.status_code}")
        results.append({"file": filename, "status": "ERROR"})

print("\n" + "="*30)
print("FINAL RESULTS")
print("="*30)
for r in results:
    print(f"{r['file']}: {r['status']} (Action: {r.get('action')}, Expected: {r.get('expected')})")
