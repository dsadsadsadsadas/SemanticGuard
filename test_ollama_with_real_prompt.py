#!/usr/bin/env python3
"""
Test Ollama with the actual Trepan prompts to see what it returns.
"""

import requests
import json

url = "http://localhost:11434/api/chat"

system_prompt = """SYSTEM: You are the TREPAN AIRBAG. You are a local security audit system for AI-assisted coding.
Your job: analyze code changes and return a JSON verdict.

Output ONLY valid JSON in this exact format:
{
  "verdict": "ACCEPT or REJECT",
  "data_flow_logic": "brief explanation",
  "chain_complete": true,
  "sinks_scanned": ["sink1", "sink2"]
}"""

user_prompt = """[SYSTEM_RULES]
Rule 1: No PII leaks

[CODE TO AUDIT]
const userEmail = req.body.email;
console.log(userEmail);

Analyze this code and return the JSON verdict."""

payload = {
    "model": "deepseek-r1:latest",
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    "stream": False,
    "options": {
        "temperature": 0.1,
        "num_ctx": 4096,
        "num_gpu": 999,
        "num_predict": 4000,  # Increased for DeepSeek R1
    }
}

print("Testing with Trepan-like prompts...")
print("\nSending request...")

try:
    response = requests.post(url, json=payload, timeout=60)
    
    if response.status_code == 200:
        data = response.json()
        content = data.get("message", {}).get("content", "")
        thinking = data.get("message", {}).get("thinking", "")
        
        print(f"\n{'='*70}")
        print(f"THINKING BLOCK ({len(thinking)} chars):")
        print(f"{'='*70}")
        print(thinking[:500])
        
        print(f"\n{'='*70}")
        print(f"CONTENT ({len(content)} chars):")
        print(f"{'='*70}")
        print(content)
        
        print(f"\n{'='*70}")
        print(f"ANALYSIS:")
        print(f"{'='*70}")
        print(f"Content length: {len(content)}")
        print(f"Has 'verdict' field: {'verdict' in content}")
        print(f"Is valid JSON: ", end="")
        try:
            parsed = json.loads(content)
            print(f"YES - {parsed}")
        except:
            print("NO")
    else:
        print(f"Error {response.status_code}: {response.text}")
        
except Exception as e:
    print(f"Exception: {e}")
