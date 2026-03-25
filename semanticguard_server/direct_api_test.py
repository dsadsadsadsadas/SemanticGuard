#!/usr/bin/env python3
"""
🛡️ SemanticGuard V2 Direct API Testing

Direct testing with real API keys - prompts user for API key and runs immediate comparison.
"""

import json
import time
import requests
import sys
import os

# Add the semanticguard_server directory to the path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_prompt_builder import (
    build_api_prompt_v1_legacy, 
    build_api_prompt_v2, 
    validate_v2_response,
    convert_v2_to_legacy_format,
    compare_v1_v2_responses
)

def get_api_config():
    """Get API configuration from user input."""
    
    print("🔑 API Configuration")
    print("=" * 30)
    print("1. OpenRouter (Claude 3.5 Sonnet) - Key starts with 'sk-or-v1-'")
    print("2. Groq (Llama 3.3 70B) - Key starts with 'gsk_'")
    print("3. OpenAI (GPT-4o-mini) - Key starts with 'sk-'")
    
    choice = input("\nSelect provider (1-3): ").strip()
    
    if choice == "1":
        api_key = input("Enter OpenRouter API key: ").strip()
        return {
            'provider': 'OpenRouter',
            'endpoint': 'https://openrouter.ai/api/v1/chat/completions',
            'model': 'anthropic/claude-3.5-sonnet',
            'headers': {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
                'HTTP-Referer': 'https://github.com/dsadsadsadsadas/SemanticGuard',
                'X-Title': 'SemanticGuard V2 Testing'
            }
        }
    elif choice == "2":
        api_key = input("Enter Groq API key: ").strip()
        return {
            'provider': 'Groq',
            'endpoint': 'https://api.groq.com/openai/v1/chat/completions',
            'model': 'llama-3.3-70b-versatile',
            'headers': {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
        }
    elif choice == "3":
        api_key = input("Enter OpenAI API key: ").strip()
        return {
            'provider': 'OpenAI',
            'endpoint': 'https://api.openai.com/v1/chat/completions',
            'model': 'gpt-4o-mini',
            'headers': {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
        }
    else:
        print("Invalid choice!")
        return None

def call_api(config, prompt_data):
    """Make API call."""
    
    payload = {
        'model': config['model'],
        'messages': [
            {'role': 'system', 'content': prompt_data['system']},
            {'role': 'user', 'content': prompt_data['user']}
        ],
        'temperature': 0.1,
        'max_tokens': 2000
    }
    
    start_time = time.time()
    
    try:
        response = requests.post(config['endpoint'], headers=config['headers'], json=payload, timeout=30)
        
        if response.status_code != 200:
            raise Exception(f"API failed: {response.status_code} - {response.text}")
        
        data = response.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        if not content:
            raise Exception("No response content")
        
        # Extract JSON from response
        import re
        
        # Remove markdown code blocks if present
        content_clean = re.sub(r'```json\s*', '', content)
        content_clean = re.sub(r'```\s*$', '', content_clean)
        
        json_match = re.search(r'\{[\s\S]*\}', content_clean)
        if not json_match:
            raise Exception("Could not extract JSON from response")
        
        # Get the JSON string
        json_str = json_match.group(0)
        
        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as e:
            # Try escaping newlines and tabs in string values
            # Replace literal newlines/tabs in JSON string values with escaped versions
            json_str_fixed = re.sub(r':\s*"([^"]*)"', lambda m: ': "' + m.group(1).replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"', json_str)
            
            try:
                result = json.loads(json_str_fixed)
            except json.JSONDecodeError:
                # Last resort: save the problematic response for debugging
                with open('debug_response.txt', 'w', encoding='utf-8') as f:
                    f.write(f"Original content:\n{content}\n\nExtracted JSON:\n{json_str}\n\nFixed JSON:\n{json_str_fixed}")
                raise Exception(f"JSON parsing failed: {e}. Debug info saved to debug_response.txt")
        
        result['api_latency'] = round(time.time() - start_time, 2)
        result['raw_response'] = content
        
        return result
        
    except Exception as e:
        return {'error': str(e), 'api_latency': round(time.time() - start_time, 2)}

def run_comparison_test(config):
    """Run V1 vs V2 comparison test."""
    
    # Test case: The problematic start_server.py subprocess usage
    test_code = '''import subprocess
import sys

def start_server():
    """Launch the FastAPI server using Uvicorn with optimized settings."""
    server_cmd = [
        sys.executable, "-m", "uvicorn", 
        "semanticguard_server.server:app", 
        "--host", "0.0.0.0", 
        "--port", "8001"
    ]
    subprocess.run(server_cmd)

def pull_model():
    """Pull Ollama model."""
    subprocess.run(["ollama", "pull", "llama3.1:8b"], check=True)
'''
    
    print(f"\n🧪 TESTING WITH {config['provider']} ({config['model']})")
    print("=" * 60)
    print("Test Case: Safe subprocess usage (should NOT be flagged)")
    print(f"Code length: {len(test_code)} characters")
    
    # Build V1 prompt
    print("\n📤 Testing V1 Prompt (Legacy)...")
    v1_prompt = build_api_prompt_v1_legacy("start_server.py", test_code)
    v1_response = call_api(config, v1_prompt)
    
    if 'error' in v1_response:
        print(f"❌ V1 API Error: {v1_response['error']}")
        return
    
    print(f"✅ V1 Response received ({v1_response['api_latency']}s)")
    print(f"   Action: {v1_response.get('action', 'UNKNOWN')}")
    print(f"   Score: {v1_response.get('drift_score', 'N/A')}")
    print(f"   Violations: {len(v1_response.get('violations', []))}")
    
    # Small delay between calls
    time.sleep(1)
    
    # Build V2 prompt
    print("\n📤 Testing V2 Prompt (Constrained)...")
    v2_prompt = build_api_prompt_v2("start_server.py", test_code)
    v2_raw_response = call_api(config, v2_prompt)
    
    if 'error' in v2_raw_response:
        print(f"❌ V2 API Error: {v2_raw_response['error']}")
        return
    
    print(f"✅ V2 Response received ({v2_raw_response['api_latency']}s)")
    
    # Process V2 response
    if 'severity' in v2_raw_response:
        # V2 format detected
        print("✅ Model followed V2 format!")
        v2_validation = validate_v2_response(v2_raw_response)
        v2_legacy = convert_v2_to_legacy_format(v2_validation["corrected_response"])
        
        print(f"   Pattern: {v2_raw_response.get('pattern_detected', 'N/A')}")
        print(f"   User Input: {v2_raw_response.get('user_controlled_input', 'N/A')}")
        print(f"   Uses Shell: {v2_raw_response.get('uses_shell', 'N/A')}")
        print(f"   Exploitability: {v2_raw_response.get('exploitability', 'N/A')}")
        print(f"   Severity: {v2_raw_response.get('severity', 'N/A')}")
        
        if v2_validation["errors"]:
            print(f"⚠️  Validation errors: {v2_validation['errors']}")
        
    else:
        # Model didn't follow V2 format
        print("⚠️  Model didn't follow V2 format, treating as V1")
        v2_legacy = v2_raw_response
        v2_validation = {"valid": False, "errors": ["Model didn't follow V2 format"]}
    
    print(f"   Final Action: {v2_legacy.get('action', 'UNKNOWN')}")
    print(f"   Final Score: {v2_legacy.get('drift_score', 'N/A')}")
    print(f"   Final Violations: {len(v2_legacy.get('violations', []))}")
    
    # Compare results
    if 'severity' in v2_raw_response:
        comparison = compare_v1_v2_responses(v1_response, v2_raw_response)
        
        print(f"\n📊 COMPARISON RESULTS:")
        print("=" * 30)
        print(f"V1 → V2 Action: {comparison['v1_action']} → {comparison['v2_action']}")
        print(f"Score Change: {comparison['v1_score']} → {comparison['v2_score']} (Δ{comparison['score_delta']:.2f})")
        
        if comparison["improvement_indicators"]:
            print(f"\n📈 IMPROVEMENTS DETECTED:")
            for improvement in comparison["improvement_indicators"]:
                print(f"  ✅ {improvement}")
        else:
            print(f"\n📈 No improvements detected")
        
        # Success criteria
        if (comparison['v1_action'] == 'REJECT' and 
            comparison['v2_action'] == 'ACCEPT' and
            v2_raw_response.get('exploitability') == 'none'):
            print(f"\n🎉 SUCCESS! V2 correctly identified safe code that V1 over-flagged!")
        elif comparison['v1_action'] == comparison['v2_action'] == 'ACCEPT':
            print(f"\n✅ Both versions correctly identified safe code")
        else:
            print(f"\n🤔 Mixed results - may need prompt tuning")
    
    # Save detailed results
    results = {
        'provider': config['provider'],
        'model': config['model'],
        'test_case': 'Safe subprocess usage',
        'v1_response': v1_response,
        'v2_raw_response': v2_raw_response,
        'v2_legacy': v2_legacy,
        'v2_validation': v2_validation,
        'timestamp': time.time()
    }
    
    filename = f"direct_api_test_results_{int(time.time())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to: {filename}")

def main():
    """Main execution."""
    
    print("🛡️ TREPAN V2 DIRECT API TESTING")
    print("=" * 40)
    print("This will test V1 vs V2 prompts with REAL API calls")
    print("to measure false positive reduction.\n")
    
    # Get API configuration
    config = get_api_config()
    if not config:
        return
    
    print(f"\n🔧 Configuration:")
    print(f"   Provider: {config['provider']}")
    print(f"   Model: {config['model']}")
    
    # Confirm before making API calls
    confirm = input(f"\n🤔 Make API calls to {config['provider']}? (y/n): ").lower().strip()
    if confirm not in ['y', 'yes']:
        print("👍 Test cancelled.")
        return
    
    # Run the test
    run_comparison_test(config)
    
    print(f"\n✅ Direct API testing complete!")

if __name__ == "__main__":
    main()