#!/usr/bin/env python3
"""Test the /initialize_project endpoint"""

import requests
import json

url = "http://127.0.0.1:8000/initialize_project"
data = {
    "mode": "solo-indie",
    "project_path": "C:/Temp/TestTrepan"
}

print(f"Testing {url}")
print(f"Request data: {json.dumps(data, indent=2)}")

try:
    response = requests.post(url, json=data, timeout=120)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
