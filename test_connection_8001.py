#!/usr/bin/env python3
"""
Quick test to verify server is accessible on port 8001
"""

import requests
import sys

def test_connection(url):
    """Test if server responds at given URL"""
    print(f"Testing: {url}")
    try:
        response = requests.get(f"{url}/health", timeout=3)
        print(f"  Status Code: {response.status_code}")
        print(f"  Response: {response.json()}")
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        print(f"  ❌ CONNECTION REFUSED")
        return False
    except requests.exceptions.Timeout:
        print(f"  ❌ TIMEOUT")
        return False
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False

print("=" * 60)
print("TREPAN SERVER CONNECTION TEST")
print("=" * 60)
print()

# Test all possible URLs
urls = [
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8001",
    "http://localhost:8000",
    "http://localhost:8001",
    "http://172.31.100.18:8000",
    "http://172.31.100.18:8001",
]

results = {}
for url in urls:
    results[url] = test_connection(url)
    print()

print("=" * 60)
print("SUMMARY")
print("=" * 60)
for url, success in results.items():
    status = "✅ WORKING" if success else "❌ FAILED"
    print(f"{status}: {url}")

print()
print("=" * 60)

# Determine what VS Code should use
working_urls = [url for url, success in results.items() if success]
if working_urls:
    print(f"✅ VS Code should use: {working_urls[0]}")
else:
    print("❌ NO WORKING SERVER FOUND")
    print("   Start server with: python start_server.py --host 0.0.0.0 --port 8001")
