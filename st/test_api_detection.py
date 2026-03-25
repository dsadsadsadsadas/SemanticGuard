#!/usr/bin/env python3
"""
Test API Detection - Verify we're getting REAL TPM from Groq API
"""

import requests
import sys
import getpass


def test_api_detection(api_key: str, model_name: str):
    """
    Test the actual API detection by making a real call to Groq.
    This will show us the EXACT headers returned by Groq.
    """
    print("=" * 70)
    print("TESTING REAL API DETECTION")
    print("=" * 70)
    print(f"\nModel: {model_name}")
    print(f"API Key: {api_key[:20]}... (masked)\n")
    
    try:
        print("🔍 Making test API call to Groq...")
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1
            },
            timeout=10
        )
        
        print(f"✅ Response Status: {response.status_code}\n")
        
        if response.status_code != 200:
            print(f"❌ API Error: {response.text}")
            return None, None
        
        # Print ALL headers
        print("📋 ALL RESPONSE HEADERS:")
        print("-" * 70)
        for key, value in response.headers.items():
            print(f"{key}: {value}")
        print("-" * 70)
        print()
        
        # Look for rate limit headers (case-insensitive)
        print("🔍 SEARCHING FOR RATE LIMIT HEADERS:")
        print("-" * 70)
        
        rpm_header = None
        tpm_header = None
        rpd_header = None
        
        # Check all possible header names (case-insensitive)
        for key, value in response.headers.items():
            key_lower = key.lower()
            
            # Look for RPM (must contain "minute" to avoid RPD confusion)
            if 'ratelimit' in key_lower and 'request' in key_lower and 'minute' in key_lower:
                print(f"✅ Found RPM header: {key} = {value}")
                rpm_header = value
            
            # Look for RPD (Requests Per Day)
            elif 'ratelimit' in key_lower and 'request' in key_lower and 'limit' in key_lower and 'minute' not in key_lower:
                print(f"⚠️  Found RPD (Requests Per Day) header: {key} = {value}")
                rpd_header = value
            
            # Look for TPM
            if 'ratelimit' in key_lower and 'token' in key_lower:
                print(f"✅ Found TPM header: {key} = {value}")
                tpm_header = value
        
        print("-" * 70)
        print()
        
        # Parse the values
        max_rpm = None
        max_tpm = None
        
        if rpm_header:
            try:
                max_rpm = int(rpm_header)
                print(f"✅ Parsed Max RPM (Requests Per Minute): {max_rpm}")
            except ValueError:
                print(f"⚠️  Could not parse RPM: {rpm_header}")
        elif rpd_header:
            try:
                rpd_value = int(rpd_header)
                print(f"⚠️  No RPM header found, only RPD (Requests Per Day): {rpd_value:,}")
                print(f"⚠️  Estimating RPM as RPD / 1440 (minutes per day)")
                max_rpm = rpd_value // 1440
                print(f"📊 Estimated Max RPM: {max_rpm}")
            except ValueError:
                print(f"⚠️  Could not parse RPD: {rpd_header}")
        else:
            print("❌ No RPM or RPD header found")
        
        if tpm_header:
            try:
                max_tpm = int(tpm_header)
                print(f"✅ Parsed Max TPM: {max_tpm:,}")
            except ValueError:
                print(f"⚠️  Could not parse TPM: {tpm_header}")
        else:
            print("❌ No TPM header found")
        
        print()
        
        # Final result
        if max_rpm and max_tpm:
            print("=" * 70)
            print("🎉 SUCCESS! API DETECTION WORKING!")
            print("=" * 70)
            print(f"Max RPM: {max_rpm}")
            print(f"Max TPM: {max_tpm:,}")
            print()
            
            # Check if it's the upgraded limit
            if max_tpm >= 500000:
                print("🚀 UPGRADED ACCOUNT DETECTED!")
                print(f"   You have {max_tpm:,} TPM (not the default 30,000)")
                print("   This is 16.7x faster than the free tier!")
            elif max_tpm == 30000:
                print("📊 Standard Llama 4 Scout limit detected (30,000 TPM)")
            else:
                print(f"📊 Custom limit detected: {max_tpm:,} TPM")
            
            return max_rpm, max_tpm
        else:
            print("=" * 70)
            print("❌ DETECTION FAILED")
            print("=" * 70)
            print("Groq API did not return rate limit headers.")
            print("This might mean:")
            print("  1. Groq changed their header format")
            print("  2. The API key is invalid")
            print("  3. The model name is incorrect")
            return None, None
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None, None


def main():
    """Main test execution"""
    print("\n🧪 GROQ API DETECTION TEST\n")
    print("This will make a REAL API call to verify we can detect your TPM limit.\n")
    
    # Get API key
    api_key = getpass.getpass("Enter your Groq API key (starts with gsk_): ")
    if not api_key:
        print("❌ API key required")
        sys.exit(1)
    
    # Model selection
    print("\nSelect model to test:")
    print("1. Llama 3.3 70B Versatile (llama-3.3-70b-versatile)")
    print("2. Llama 4 Scout 17B (meta-llama/llama-4-scout-17b-16e-instruct)")
    
    choice = input("\nChoice (1 or 2): ").strip()
    
    if choice == "1":
        model_name = "llama-3.3-70b-versatile"
    elif choice == "2":
        model_name = "meta-llama/llama-4-scout-17b-16e-instruct"
    else:
        print("❌ Invalid choice")
        sys.exit(1)
    
    print()
    
    # Run the test
    max_rpm, max_tpm = test_api_detection(api_key, model_name)
    
    if max_rpm and max_tpm:
        print("\n" + "=" * 70)
        print("VERIFICATION COMPLETE")
        print("=" * 70)
        print(f"✅ API detection is working correctly")
        print(f"✅ Your actual limit: {max_tpm:,} TPM")
        print(f"✅ This is NOT hardcoded - it came from Groq's API")
        print()
        
        # Show what this means for auditing
        print("📊 AUDIT SPEED CALCULATION:")
        print("-" * 70)
        
        # Example: 150 files, 5000 tokens each
        total_tokens = 150 * 5000
        time_seconds = (total_tokens / max_tpm) * 60
        time_minutes = time_seconds / 60
        
        print(f"For 150 files @ 5,000 tokens each ({total_tokens:,} total tokens):")
        print(f"  Estimated time: {time_minutes:.1f} minutes")
        print(f"  That's {150 / time_minutes:.1f} files per minute!")
        print()
        
        if max_tpm >= 500000:
            print("🚀 With your upgraded 500k TPM:")
            print("   You can audit MASSIVE codebases in minutes!")
            print("   This is production-grade speed.")
        
        print("\n✅ SUCCESS - API detection verified!\n")
    else:
        print("\n❌ FAILED - Could not detect TPM from API\n")
        print("Possible solutions:")
        print("1. Check your API key is valid")
        print("2. Verify the model name is correct")
        print("3. Check Groq's API documentation for header changes")


if __name__ == "__main__":
    main()
