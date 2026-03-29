#!/usr/bin/env python3
"""
Groq API Header Diagnostic Script

This script makes a minimal API call to Groq and prints ALL response headers
to help diagnose rate limit detection issues.

Usage:
    python test_groq_headers.py
"""

import requests
import os
import sys

def test_groq_headers():
    """
    Make a minimal Groq API call and print all response headers.
    """
    # Get API key from environment
    api_key = os.environ.get('GROQ_API_KEY')
    
    if not api_key:
        print("❌ ERROR: GROQ_API_KEY environment variable not set")
        print("\nPlease set your API key:")
        print("  export GROQ_API_KEY='your-api-key-here'")
        sys.exit(1)
    
    model = "meta-llama/llama-4-scout-17b-16e-instruct"
    
    print("=" * 80)
    print("GROQ API HEADER DIAGNOSTIC")
    print("=" * 80)
    print(f"Model: {model}")
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print("=" * 80)
    print()
    
    try:
        print("Making API call to Groq...")
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1
            },
            timeout=10
        )
        
        print(f"✅ Response Status: {response.status_code}")
        print()
        
        # Print ALL headers
        print("=" * 80)
        print("ALL RESPONSE HEADERS")
        print("=" * 80)
        
        if not response.headers:
            print("⚠️ No headers returned!")
        else:
            for key, value in response.headers.items():
                print(f"{key}: {value}")
        
        print()
        print("=" * 80)
        print("RATE LIMIT HEADERS ONLY")
        print("=" * 80)
        
        rate_limit_headers = {}
        for key, value in response.headers.items():
            key_lower = key.lower()
            if 'rate' in key_lower or 'limit' in key_lower:
                rate_limit_headers[key] = value
                print(f"✅ {key}: {value}")
        
        if not rate_limit_headers:
            print("⚠️ No rate limit headers found!")
        
        print()
        print("=" * 80)
        print("DETECTION LOGIC")
        print("=" * 80)
        
        # Try to detect TPM
        tpm = None
        tpm_header = None
        for key, value in response.headers.items():
            key_lower = key.lower()
            if 'ratelimit' in key_lower and 'token' in key_lower and 'limit' in key_lower:
                try:
                    tpm = int(value)
                    tpm_header = key
                    break
                except ValueError:
                    pass
        
        if tpm:
            print(f"✅ TPM Detected: {tpm:,} (from header: {tpm_header})")
        else:
            print("❌ TPM NOT DETECTED")
        
        # Try to detect RPM
        rpm = None
        rpm_header = None
        
        # Pattern 1: Look for "minute" in header name
        for key, value in response.headers.items():
            key_lower = key.lower()
            if ('ratelimit' in key_lower or 'rate-limit' in key_lower) and \
               'request' in key_lower and \
               ('limit' in key_lower or 'remaining' in key_lower) and \
               'minute' in key_lower:
                try:
                    rpm = int(value)
                    rpm_header = key
                    print(f"✅ RPM Detected (Pattern 1 - with 'minute'): {rpm:,} (from header: {rpm_header})")
                    break
                except ValueError:
                    pass
        
        # Pattern 2: If no "minute" header, look for any request limit
        if not rpm:
            for key, value in response.headers.items():
                key_lower = key.lower()
                if ('ratelimit' in key_lower or 'rate-limit' in key_lower) and \
                   'request' in key_lower and \
                   ('limit' in key_lower or 'remaining' in key_lower):
                    try:
                        potential_rpm = int(value)
                        # Check if this looks like RPD (requests per day)
                        if potential_rpm > 10000:
                            estimated_rpm = potential_rpm // 1440
                            print(f"⚠️ Found RPD (Requests Per Day): {potential_rpm:,} (from header: {key})")
                            print(f"⚠️ Estimated RPM: {estimated_rpm} (RPD / 1440 minutes)")
                            rpm = estimated_rpm
                            rpm_header = key
                        else:
                            rpm = potential_rpm
                            rpm_header = key
                            print(f"✅ RPM Detected (Pattern 2 - without 'minute'): {rpm:,} (from header: {rpm_header})")
                        break
                    except ValueError:
                        pass
        
        if not rpm:
            print("❌ RPM NOT DETECTED")
        
        print()
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"TPM: {tpm:,} tokens/minute" if tpm else "TPM: NOT DETECTED")
        print(f"RPM: {rpm:,} requests/minute" if rpm else "RPM: NOT DETECTED")
        
        if tpm and rpm:
            print()
            print("✅ Both TPM and RPM detected successfully!")
            if tpm >= 100000:
                print(f"🚀 PRO ACCOUNT DETECTED! You have {tpm:,} TPM")
        else:
            print()
            print("❌ Detection failed - some limits could not be determined")
        
        print("=" * 80)
        
    except requests.exceptions.Timeout:
        print("❌ ERROR: Request timed out")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_groq_headers()
