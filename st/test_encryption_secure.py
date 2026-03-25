#!/usr/bin/env python3
"""
Quick test to verify encryption_secure.py is flagged as SAFE
"""
import os
import sys
import json
import requests
import getpass
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from stress_test import GroqAuditClient, TokenBucket

def test_single_file():
    """Test encryption_secure.py specifically"""
    
    # Get API key from environment or prompt
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        print("🔑 Enter Groq API key:")
        api_key = getpass.getpass("→ ")
    
    # Configuration
    model = "meta-llama/llama-4-scout-17b-16e-instruct"
    max_rpm = 347
    max_tpm = 300000
    
    # Initialize
    rate_limiter = TokenBucket(max_rpm, max_tpm)
    client = GroqAuditClient(api_key, model, rate_limiter)
    
    # Test file
    test_file = Path("../Final_Test/encryption_secure.py")
    
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        sys.exit(1)
    
    print(f"🧪 Testing: {test_file.name}")
    print(f"Model: {model}\n")
    
    # Run audit
    import asyncio
    result = asyncio.run(client.audit_file(test_file))
    
    # Analyze result
    print("\n" + "="*60)
    print("📊 RESULT")
    print("="*60)
    
    status = result.get("status")
    finding = result.get("finding")
    
    print(f"Status: {status}")
    
    if status == "vulnerable":
        print(f"❌ FALSE POSITIVE DETECTED!")
        print(f"Finding: {finding}")
        print("\n⚠️  The LLM incorrectly flagged os.getenv() as a hardcoded secret.")
        print("⚠️  Prompt update FAILED. Need to refine the system prompt.")
        return False
    elif status == "safe":
        print(f"✅ CORRECT! File marked as SAFE")
        print("✅ The LLM correctly recognized os.getenv() as secure.")
        return True
    elif status == "error":
        print(f"⚠️  Error occurred: {result.get('error')}")
        return False
    else:
        print(f"⚠️  Unknown status: {status}")
        return False

if __name__ == "__main__":
    success = test_single_file()
    sys.exit(0 if success else 1)
