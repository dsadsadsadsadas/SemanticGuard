#!/usr/bin/env python3
"""
Direct Ollama API test to see what's happening.
"""

import requests
import json

url = "http://localhost:11434/api/chat"

# Minimal test
payload = {
    "model": "deepseek-r1:latest",
    "messages": [
        {
            "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "Say hello in JSON format: {\"message\": \"your response here\"}"
        }
    ],
    "stream": False,
    "options": {
        "temperature": 0.1,
        "num_ctx": 4096,
        "num_gpu": 999,
        "num_predict": 800,
    }
}

print("Testing deepseek-r1:latest with /api/chat endpoint...")
print(f"Payload: {json.dumps(payload, indent=2)}")
print("\nSending request...")

try:
    response = requests.post(url, json=payload, timeout=60)
    print(f"\nStatus: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nFull response:")
        print(json.dumps(data, indent=2))
        
        content = data.get("message", {}).get("content", "")
        print(f"\nContent length: {len(content)}")
        print(f"Content: {content}")
    else:
        print(f"Error: {response.text}")
        
except Exception as e:
    print(f"Exception: {e}")
