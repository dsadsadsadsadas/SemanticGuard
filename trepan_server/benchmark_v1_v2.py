#!/usr/bin/env python3
"""
benchmark_v1_v2.py

Adversarial benchmark: V1 Legacy Prompt vs V2 Constrained Prompt
Tests 20 scenarios designed to expose V1's weaknesses and validate V2's improvements.

Run: python trepan_server/benchmark_v1_v2.py
Requires: GROQ_API_KEY or OPENROUTER_API_KEY environment variable
"""

import os
import json
import time
import requests
import statistics
from typing import Dict, Any, List

# ── CONFIG ────────────────────────────────────────────────────────────────────

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = {
    "1": {"name": "llama-3.3-70b-versatile", "display": "Llama 3.3 70B Versatile", "tpm": 12000},
    "2": {"name": "meta-llama/llama-4-scout-17b-16e-instruct", "display": "Llama 4 Scout 17B", "tpm": 30000}
}

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "anthropic/claude-3.5-sonnet"

# Auto-detect provider from environment or prompt user
if os.environ.get("GROQ_API_KEY"):
    API_KEY = os.environ["GROQ_API_KEY"]
    API_URL = GROQ_API_URL
    PROVIDER = "Groq"
    
    # Let user choose Groq model
    print("\n" + "="*70)
    print("GROQ MODEL SELECTION")
    print("="*70)
    print("\nAvailable Groq models:")
    for key, model_info in GROQ_MODELS.items():
        print(f"  {key}. {model_info['display']} ({model_info['tpm']:,} TPM)")
    
    model_choice = input("\nSelect model (1 or 2): ").strip()
    if model_choice in GROQ_MODELS:
        MODEL = GROQ_MODELS[model_choice]["name"]
        MODEL_TPM = GROQ_MODELS[model_choice]["tpm"]
        MODEL_DISPLAY = GROQ_MODELS[model_choice]["display"]
    else:
        print("Invalid choice, using default (Llama 3.3 70B)")
        MODEL = GROQ_MODELS["1"]["name"]
        MODEL_TPM = GROQ_MODELS["1"]["tpm"]
        MODEL_DISPLAY = GROQ_MODELS["1"]["display"]
    
    print(f"\n✓ Using {MODEL_DISPLAY} (Rate limit: {MODEL_TPM:,} TPM)\n")
    
elif os.environ.get("OPENROUTER_API_KEY"):
    API_KEY = os.environ["OPENROUTER_API_KEY"]
    API_URL = OPENROUTER_API_URL
    MODEL = OPENROUTER_MODEL
    MODEL_TPM = 100000  # OpenRouter has higher limits
    MODEL_DISPLAY = "Claude 3.5 Sonnet"
    PROVIDER = "OpenRouter"
    print(f"\n✓ Using OpenRouter with {MODEL_DISPLAY}\n")
    
else:
    # Prompt user for API key
    import getpass
    print("\n" + "="*70)
    print("API KEY REQUIRED")
    print("="*70)
    print("\nNo API key found in environment variables.")
    print("\nAvailable providers:")
    print("  1. Groq (multiple models)")
    print("  2. OpenRouter (claude-3.5-sonnet)")
    
    choice = input("\nSelect provider (1 or 2): ").strip()
    
    if choice == "1":
        PROVIDER = "Groq"
        API_URL = GROQ_API_URL
        API_KEY = getpass.getpass("Enter Groq API Key (starts with gsk_): ")
        
        # Let user choose Groq model
        print("\nAvailable Groq models:")
        for key, model_info in GROQ_MODELS.items():
            print(f"  {key}. {model_info['display']} ({model_info['tpm']:,} TPM)")
        
        model_choice = input("\nSelect model (1 or 2): ").strip()
        if model_choice in GROQ_MODELS:
            MODEL = GROQ_MODELS[model_choice]["name"]
            MODEL_TPM = GROQ_MODELS[model_choice]["tpm"]
            MODEL_DISPLAY = GROQ_MODELS[model_choice]["display"]
        else:
            print("Invalid choice, using default (Llama 3.3 70B)")
            MODEL = GROQ_MODELS["1"]["name"]
            MODEL_TPM = GROQ_MODELS["1"]["tpm"]
            MODEL_DISPLAY = GROQ_MODELS["1"]["display"]
            
    elif choice == "2":
        PROVIDER = "OpenRouter"
        API_URL = OPENROUTER_API_URL
        MODEL = OPENROUTER_MODEL
        MODEL_TPM = 100000
        MODEL_DISPLAY = "Claude 3.5 Sonnet"
        API_KEY = getpass.getpass("Enter OpenRouter API Key (starts with sk-or-v1-): ")
    else:
        raise ValueError("Invalid choice. Enter 1 or 2.")
    
    if not API_KEY or len(API_KEY) < 10:
        raise ValueError("Invalid API key provided.")
    
    print(f"\n✓ Using {PROVIDER} with {MODEL_DISPLAY} (Rate limit: {MODEL_TPM:,} TPM)\n")

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from trepan_server.api_prompt_builder import (
    build_api_prompt_v1_legacy,
    build_api_prompt_v2,
    build_api_prompt_v2_fast,
    validate_v2_response,
    convert_v2_to_legacy_format
)

# ── ADVERSARIAL TEST CASES ────────────────────────────────────────────────────

TEST_CASES = [
    
    # ── TRAPS FOR V1 (should NOT flag) ───────────────────────────────────────
    # V1 is expected to false-positive on these. V2 should ACCEPT.
    
    {
        "id": "FP1",
        "name": "subprocess with shell=False and list args",
        "expected": "ACCEPT",
        "trap": "V1 sees subprocess and panics",
        "code": """
import subprocess
result = subprocess.run(
    ["git", "status", "--short"],
    capture_output=True,
    shell=False,
    text=True
)
print(result.stdout)
"""
    },
    {
        "id": "FP2",
        "name": "eval on a hardcoded math expression",
        "expected": "ACCEPT",
        "trap": "V1 sees eval() and panics",
        "code": """
SAFE_EXPRESSIONS = ["2 + 2", "10 * 5", "100 / 4"]
for expr in SAFE_EXPRESSIONS:
    result = eval(expr)
    print(f"{expr} = {result}")
"""
    },
    {
        "id": "FP3",
        "name": "SQL query with parameterized statement",
        "expected": "ACCEPT",
        "trap": "V1 sees db.execute and flags string concatenation",
        "code": """
def get_user(conn, user_id: int):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, email FROM users WHERE id = ?",
        (user_id,)
    )
    return cursor.fetchone()
"""
    },
    {
        "id": "FP4",
        "name": "logging sensitive field name but not value",
        "expected": "ACCEPT",
        "trap": "V1 sees 'password' in log statement and flags it",
        "code": """
import logging
logger = logging.getLogger(__name__)

def update_password(user_id: int):
    logger.info(f"Password update requested for user_id={user_id}")
    db.update_password_hash(user_id, generate_new_hash())
    logger.info("Password update complete")
"""
    },
    {
        "id": "FP5",
        "name": "pickle loading from trusted internal file",
        "expected": "ACCEPT",
        "trap": "V1 sees pickle.load and flags remote code execution",
        "code": """
import pickle
import pathlib

MODEL_PATH = pathlib.Path("models/trained_classifier.pkl")
assert MODEL_PATH.exists(), "Model file missing"

with open(MODEL_PATH, "rb") as f:
    model = pickle.load(f)

predictions = model.predict(test_data)
"""
    },
    {
        "id": "FP6",
        "name": "os.system with hardcoded safe command",
        "expected": "ACCEPT",
        "trap": "V1 sees os.system and auto-rejects",
        "code": """
import os

def clear_build_artifacts():
    os.system("rm -rf ./build ./dist ./__pycache__")
    print("Build artifacts cleared")
"""
    },
    {
        "id": "FP7",
        "name": "regex with user pattern matching",
        "expected": "ACCEPT",
        "trap": "V1 sees user input and flags it",
        "code": """
import re

def validate_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

user_email = request.form.get('email', '')
if not validate_email(user_email):
    return {"error": "Invalid email format"}, 400
"""
    },
    {
        "id": "FP8",
        "name": "hashlib with user password",
        "expected": "ACCEPT",
        "trap": "V1 sees user password flowing somewhere and flags",
        "code": """
import hashlib
import secrets

def hash_password(raw_password: str) -> str:
    salt = secrets.token_hex(32)
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        raw_password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return f"{salt}:{hashed.hex()}"

user_password = request.json.get('password')
stored_hash = hash_password(user_password)
db.save_user_hash(user_id, stored_hash)
"""
    },
    
    # ── TRAPS FOR V2 (MUST flag) ──────────────────────────────────────────────
    # V2's conservative bias could make it ACCEPT these. Both should REJECT.
    
    {
        "id": "TP1",
        "name": "subprocess with shell=True and user input",
        "expected": "REJECT",
        "trap": "V2 might be too conservative and accept",
        "code": """
import subprocess

def run_user_command(user_input: str):
    result = subprocess.run(
        f"echo {user_input}",
        shell=True,
        capture_output=True
    )
    return result.stdout.decode()
"""
    },
    {
        "id": "TP2",
        "name": "eval with direct user input",
        "expected": "REJECT",
        "trap": "V2 anti-hallucination might make it doubt the violation",
        "code": """
from flask import request

@app.route('/calculate')
def calculate():
    expression = request.args.get('expr')
    result = eval(expression)
    return str(result)
"""
    },
    {
        "id": "TP3",
        "name": "SQL with f-string and request param",
        "expected": "REJECT",
        "trap": "V2 might classify as theoretical not real",
        "code": """
def search_users(conn, search_term: str):
    query = f"SELECT * FROM users WHERE name LIKE '%{search_term}%'"
    return conn.execute(query).fetchall()

term = request.args.get('search')
results = search_users(db, term)
"""
    },
    {
        "id": "TP4",
        "name": "hardcoded AWS secret key",
        "expected": "REJECT",
        "trap": "V2 treats hardcoded constants as safe by default",
        "code": """
import boto3

AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)
"""
    },
    {
        "id": "TP5",
        "name": "password in plaintext log",
        "expected": "REJECT",
        "trap": "V2 might not consider logging a real sink",
        "code": """
import logging
logger = logging.getLogger(__name__)

def login(username: str, password: str) -> bool:
    logger.debug(f"Login attempt: user={username}, pass={password}")
    return db.verify_credentials(username, password)
"""
    },
    {
        "id": "TP6",
        "name": "pickle load from user-supplied bytes",
        "expected": "REJECT",
        "trap": "V2 might see it as low severity",
        "code": """
import pickle
from flask import request

@app.route('/restore')
def restore_session():
    session_data = request.get_data()
    user_obj = pickle.loads(session_data)
    return jsonify(user_obj.to_dict())
"""
    },
    {
        "id": "TP7",
        "name": "request data printed to debug log",
        "expected": "REJECT",
        "trap": "V2 might accept because it goes to a logger not print",
        "code": """
from flask import request
import logging
logger = logging.getLogger(__name__)

@app.route('/payment', methods=['POST'])
def process_payment():
    card_data = request.json
    logger.info(f"Processing payment: {card_data}")
    return charge_card(card_data)
"""
    },
    {
        "id": "TP8",
        "name": "multi-hop: input to variable to SQL",
        "expected": "REJECT",
        "trap": "V2 5-step process might lose the thread across hops",
        "code": """
def get_report(conn, filters):
    user_id = filters.get('user_id')
    date_range = filters.get('date_range')
    query = "SELECT * FROM reports WHERE user_id=" + str(user_id)
    if date_range:
        query += f" AND date BETWEEN '{date_range[0]}' AND '{date_range[1]}'"
    return conn.execute(query).fetchall()

user_filters = request.json
results = get_report(db_conn, user_filters)
"""
    },
    
    # ── AMBIGUOUS EDGE CASES ──────────────────────────────────────────────────
    # Both models will disagree. The correct answer requires context judgment.
    
    {
        "id": "E1",
        "name": "subprocess with variable command but controlled list",
        "expected": "ACCEPT",
        "trap": "Command is dynamic but still a safe list",
        "code": """
import subprocess

ALLOWED_COMMANDS = {
    "lint": ["pylint", "--disable=C0111"],
    "test": ["pytest", "-v", "--tb=short"],
    "format": ["black", "--check", "."]
}

def run_tool(tool_name: str):
    if tool_name not in ALLOWED_COMMANDS:
        raise ValueError(f"Unknown tool: {tool_name}")
    cmd = ALLOWED_COMMANDS[tool_name]
    return subprocess.run(cmd, shell=False, capture_output=True)
"""
    },
    {
        "id": "E2",
        "name": "error message includes user input but sanitized",
        "expected": "ACCEPT",
        "trap": "User input in error response but escaped",
        "code": """
import html
from flask import request, jsonify

@app.route('/search')
def search():
    query = request.args.get('q', '')
    safe_query = html.escape(query)
    
    if len(safe_query) > 100:
        return jsonify({
            "error": f"Query too long: '{safe_query[:20]}...'"
        }), 400
    
    return jsonify({"results": db.search(safe_query)})
"""
    },
    {
        "id": "E3",
        "name": "JWT token decoded and re-encoded",
        "expected": "ACCEPT",
        "trap": "Auth token flows through multiple steps",
        "code": """
import jwt
from flask import request

SECRET = os.environ.get("JWT_SECRET")

@app.route('/refresh')
def refresh_token():
    old_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = jwt.decode(old_token, SECRET, algorithms=['HS256'])
    payload['exp'] = int(time.time()) + 3600
    new_token = jwt.encode(payload, SECRET, algorithm='HS256')
    return jsonify({"token": new_token})
"""
    },
    {
        "id": "E4",
        "name": "environment variable used in SQL",
        "expected": "REJECT",
        "trap": "Env vars are not user input but this creates SQL injection",
        "code": """
import os

DB_TABLE = os.environ.get("REPORT_TABLE", "reports")

def get_all_records(conn):
    query = f"SELECT * FROM {DB_TABLE} WHERE active = 1"
    return conn.execute(query).fetchall()
"""
    },
    
    # ── PROMPT BLIND SPOT ANALYSIS ─────────────────────────────────────────
    # These are the 4 cases BOTH models failed. We test variations to isolate
    # whether the V2 prompt rule is the cause or the model itself.
    
    {
        "id": "BS1a",
        "name": "TP4 variation — AWS key in variable not constant",
        "expected": "REJECT",
        "trap": "If V2 flags this but not TP4, the issue is the CONSTANT rule",
        "code": """
import boto3
import os

aws_key = "AKIAIOSFODNN7EXAMPLE"
aws_secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

client = boto3.client(
    's3',
    aws_access_key_id=aws_key,
    aws_secret_access_key=aws_secret
)
"""
    },
    {
        "id": "BS1b",
        "name": "TP4 variation — AWS key explicitly labeled as secret",
        "expected": "REJECT",
        "trap": "If V2 flags this, adding word SECRET triggers the rule",
        "code": """
import boto3

SECRET_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
SECRET_AWS_TOKEN = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

client = boto3.client('s3',
    aws_access_key_id=SECRET_AWS_KEY,
    aws_secret_access_key=SECRET_AWS_TOKEN
)
"""
    },
    {
        "id": "BS2a",
        "name": "TP5 variation — password logged via print not logger",
        "expected": "REJECT",
        "trap": "If V2 flags print but not logger.debug, the issue is sink recognition",
        "code": """
def login(username: str, password: str) -> bool:
    print(f"Login attempt: user={username}, pass={password}")
    return db.verify_credentials(username, password)
"""
    },
    {
        "id": "BS2b",
        "name": "TP5 variation — password logged with explicit PHI label",
        "expected": "REJECT",
        "trap": "If adding PHI label triggers the rule, the prompt needs explicit logging sink rules",
        "code": """
import logging
logger = logging.getLogger(__name__)

def login(username: str, password: str) -> bool:
    # PHI WARNING: This logs sensitive credential data
    logger.debug(f"Login attempt: user={username}, pass={password}")
    return db.verify_credentials(username, password)
"""
    },
    {
        "id": "BS3a",
        "name": "E4 variation — env var used in LIKE clause",
        "expected": "REJECT",
        "trap": "If V2 catches LIKE but not FROM, the issue is SQL pattern matching depth",
        "code": """
import os
TABLE_FILTER = os.environ.get("SEARCH_FILTER", "active")

def get_records(conn):
    query = f"SELECT * FROM users WHERE status LIKE '%{TABLE_FILTER}%'"
    return conn.execute(query).fetchall()
"""
    },
    {
        "id": "BS3b",
        "name": "E4 variation — env var concatenated with user input",
        "expected": "REJECT",
        "trap": "Combined env var + user input should definitely be REJECT",
        "code": """
import os
from flask import request

BASE_TABLE = os.environ.get("BASE_TABLE", "reports")
user_filter = request.args.get("filter")
query = f"SELECT * FROM {BASE_TABLE} WHERE category='{user_filter}'"
results = db.execute(query).fetchall()
"""
    },
]

# ── API CALL ──────────────────────────────────────────────────────────────────

def call_api(system: str, user: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 0.1,
        "max_tokens": 800
    }
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            t = time.perf_counter()
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            elapsed = time.perf_counter() - t
            
            resp_json = resp.json()
            
            # Check for API errors
            if "error" in resp_json:
                error_msg = resp_json["error"].get("message", str(resp_json["error"]))
                
                # Check if it's a rate limit error
                if "rate limit" in error_msg.lower():
                    # Extract wait time from error message if available
                    import re
                    wait_match = re.search(r'try again in ([\d.]+)([ms])', error_msg)
                    if wait_match:
                        wait_value = float(wait_match.group(1))
                        wait_unit = wait_match.group(2)
                        wait_time = wait_value if wait_unit == 's' else wait_value / 1000
                        wait_time = max(wait_time, 1.0) + 0.5  # Add buffer
                    else:
                        wait_time = 3 ** attempt  # Exponential: 1, 3, 9, 27
                    
                    if attempt < max_retries - 1:
                        print(f"   ⏳ Rate limited. Waiting {wait_time:.1f}s... (attempt {attempt + 2}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        return {"content": '{"action": "ACCEPT", "drift_score": 0.0, "reasoning": "Rate limit exceeded", "violations": []}', "elapsed": elapsed}
                else:
                    print(f"\n⚠️  API Error: {error_msg}")
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"   Retrying in {wait_time}s... (attempt {attempt + 2}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        return {"content": '{"action": "ACCEPT", "drift_score": 0.0, "reasoning": "API error", "violations": []}', "elapsed": elapsed}
            
            # Extract content
            if "choices" not in resp_json:
                print(f"\n⚠️  Unexpected API response format: {resp_json}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"   Retrying in {wait_time}s... (attempt {attempt + 2}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    return {"content": '{"action": "ACCEPT", "drift_score": 0.0, "reasoning": "Invalid response", "violations": []}', "elapsed": elapsed}
            
            content = resp_json["choices"][0]["message"]["content"]
            return {"content": content, "elapsed": elapsed}
            
        except requests.exceptions.Timeout:
            print(f"\n⚠️  Request timeout")
            if attempt < max_retries - 1:
                print(f"   Retrying... (attempt {attempt + 2}/{max_retries})")
                time.sleep(2)
                continue
            else:
                return {"content": '{"action": "ACCEPT", "drift_score": 0.0, "reasoning": "Timeout", "violations": []}', "elapsed": 60.0}
        
        except requests.exceptions.RequestException as e:
            print(f"\n⚠️  Network error: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"   Retrying in {wait_time}s... (attempt {attempt + 2}/{max_retries})")
                time.sleep(wait_time)
                continue
            else:
                return {"content": '{"action": "ACCEPT", "drift_score": 0.0, "reasoning": "Network error", "violations": []}', "elapsed": 0.0}
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Benchmark interrupted by user")
            raise
        
        except Exception as e:
            print(f"\n⚠️  Unexpected error: {e}")
            if attempt < max_retries - 1:
                print(f"   Retrying... (attempt {attempt + 2}/{max_retries})")
                time.sleep(1)
                continue
            else:
                return {"content": '{"action": "ACCEPT", "drift_score": 0.0, "reasoning": "Error", "violations": []}', "elapsed": 0.0}
    
    # Should never reach here
    return {"content": '{"action": "ACCEPT", "drift_score": 0.0, "reasoning": "Max retries exceeded", "violations": []}', "elapsed": 0.0}

def parse_json_response(raw: str) -> Dict[str, Any]:
    import re
    
    # Remove markdown code blocks
    clean = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    clean = re.sub(r'\s*```$', '', clean)
    clean = clean.strip()
    
    # Try direct parse first
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON object
    json_match = re.search(r'\{.*\}', clean, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        
        # Fix common JSON issues with control characters in strings
        # Replace literal newlines in string values with \n
        try:
            # Use json.loads with strict=False to be more lenient
            return json.loads(json_str, strict=False)
        except json.JSONDecodeError:
            pass
        
        # Try fixing control characters manually
        try:
            # Replace unescaped newlines and tabs in string values
            fixed = re.sub(r'("reasoning":\s*"[^"]*)"(\s+)', r'\1\\n\2', json_str)
            fixed = re.sub(r'("pattern_detected":\s*"[^"]*)"(\s+)', r'\1\\n\2', fixed)
            fixed = re.sub(r'("violation":\s*"[^"]*)"(\s+)', r'\1\\n\2', fixed)
            return json.loads(fixed, strict=False)
        except:
            pass
        
        # Last resort: try to manually fix the JSON
        try:
            # Replace all control characters in string values
            import codecs
            fixed = codecs.decode(json_str, 'unicode_escape')
            return json.loads(fixed, strict=False)
        except:
            pass
    
    # If all parsing fails, save the raw response for debugging
    debug_file = f"benchmark_parse_error_{int(time.time())}.txt"
    try:
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(f"Raw response:\n{raw}\n\n")
            f.write(f"Cleaned:\n{clean}\n")
        print(f"\n⚠️  JSON parse failed - saved to {debug_file}")
    except:
        print(f"\n⚠️  JSON parse failed")
        print(f"   Raw (first 300 chars): {raw[:300]}")
    
    # Return safe default
    return {
        "action": "ACCEPT",
        "drift_score": 0.0,
        "reasoning": "Failed to parse response",
        "violations": [],
        "severity": "NONE",
        "exploitability": "none",
        "confidence": 0.0,
        "pattern_detected": "parse_error",
        "user_controlled_input": False,
        "uses_shell": False,
        "argument_type": "none"
    }

def get_v1_verdict(response: Dict) -> str:
    return response.get("action", "UNKNOWN")

def get_v2_verdict(response: Dict) -> str:
    severity = response.get("severity", "NONE")
    return "REJECT" if severity in ["CRITICAL", "HIGH", "MEDIUM"] else "ACCEPT"

# ── BENCHMARK RUNNER ──────────────────────────────────────────────────────────

def run_benchmark():
    # Calculate optimal delay based on model TPM
    if PROVIDER == "Groq":
        # Higher TPM = shorter delay
        if MODEL_TPM >= 30000:
            delay_between_calls = 0.8
            delay_between_tests = 0.8
        elif MODEL_TPM >= 20000:
            delay_between_calls = 1.0
            delay_between_tests = 1.0
        else:  # 12000 TPM
            delay_between_calls = 1.5
            delay_between_tests = 1.5
    else:
        delay_between_calls = 0.5
        delay_between_tests = 0.5
    
    total_delay = delay_between_calls + delay_between_tests
    estimated_time = len(TEST_CASES) * (total_delay + 2.0)  # +2s for avg API response time
    
    print(f"\n{'='*70}")
    print(f"TREPAN API PROMPT BENCHMARK — V1 Legacy vs V2 Constrained")
    print(f"Provider: {PROVIDER} | Model: {MODEL_DISPLAY}")
    print(f"Tests: {len(TEST_CASES)} adversarial scenarios")
    print(f"{'='*70}")
    
    if PROVIDER == "Groq":
        print(f"\n⚠️  Rate limit: {MODEL_TPM:,} tokens/minute")
        print(f"   Delay: {total_delay:.1f}s between tests (estimated time: {estimated_time/60:.1f} min)")
    
    print()
    
    results_v1 = []
    results_v2 = []
    results_v3 = []
    
    for idx, test in enumerate(TEST_CASES):
        print(f"[{test['id']}] {test['name']} ({idx + 1}/{len(TEST_CASES)})")
        print(f"     Trap: {test['trap']}")
        print(f"     Expected: {test['expected']}")
        
        # V1
        p1 = build_api_prompt_v1_legacy(f"{test['id']}.py", test['code'])
        r1 = call_api(p1["system"], p1["user"])
        parsed_v1 = parse_json_response(r1["content"])
        verdict_v1 = get_v1_verdict(parsed_v1)
        correct_v1 = verdict_v1 == test["expected"]
        
        # Add delay between V1 and V2 to avoid rate limiting
        if PROVIDER == "Groq":
            time.sleep(delay_between_calls)
        
        # V2
        p2 = build_api_prompt_v2(f"{test['id']}.py", test['code'])
        r2 = call_api(p2["system"], p2["user"])
        parsed_v2 = parse_json_response(r2["content"])
        verdict_v2 = get_v2_verdict(parsed_v2)
        correct_v2 = verdict_v2 == test["expected"]
        
        v2_exploitability = parsed_v2.get("exploitability", "?")
        v2_severity = parsed_v2.get("severity", "?")
        
        # Add delay before V2_FAST
        if PROVIDER == "Groq":
            time.sleep(delay_between_calls)
        
        # V2 Fast
        p3 = build_api_prompt_v2_fast(f"{test['id']}.py", test['code'])
        r3 = call_api(p3["system"], p3["user"])
        parsed_v3_raw = parse_json_response(r3["content"])
        
        # V2 Fast uses compressed 4-field schema - handle both dict and list responses
        if isinstance(parsed_v3_raw, dict):
            severity_v3 = parsed_v3_raw.get("severity", "NONE")
            v3_exploit = parsed_v3_raw.get("exploitability", "?")
        else:
            # Fallback for malformed responses
            severity_v3 = "NONE"
            v3_exploit = "?"
        
        verdict_v3 = "REJECT" if severity_v3 in ["CRITICAL", "HIGH", "MEDIUM"] else "ACCEPT"
        correct_v3 = verdict_v3 == test["expected"]
        
        status_v1 = "✅" if correct_v1 else "❌"
        status_v2 = "✅" if correct_v2 else "❌"
        status_v3 = "✅" if correct_v3 else "❌"
        
        print(f"     V1:  {verdict_v1} {status_v1} ({r1['elapsed']:.1f}s)")
        print(f"     V2:  {verdict_v2} {status_v2} ({r2['elapsed']:.1f}s) | exploit={v2_exploitability} | severity={v2_severity}")
        print(f"     V2F: {verdict_v3} {status_v3} ({r3['elapsed']:.1f}s) | exploit={v3_exploit} | severity={severity_v3}")
        
        if correct_v1 != correct_v2 or correct_v2 != correct_v3:
            winners = []
            if correct_v1 and not correct_v2: winners.append("V1")
            if correct_v2 and not correct_v1: winners.append("V2")
            if correct_v3 and not correct_v1 and not correct_v2: winners.append("V2F")
            if winners:
                print(f"     ⚡ {' & '.join(winners)} WIN — disagreement on this case")
        
        print()
        
        results_v1.append({"id": test["id"], "correct": correct_v1, "verdict": verdict_v1,
                           "expected": test["expected"], "elapsed": r1["elapsed"],
                           "category": test["id"][:2]})
        results_v2.append({"id": test["id"], "correct": correct_v2, "verdict": verdict_v2,
                           "expected": test["expected"], "elapsed": r2["elapsed"],
                           "exploitability": v2_exploitability, "severity": v2_severity,
                           "category": test["id"][:2]})
        
        results_v3.append({"id": test["id"], "correct": correct_v3, "verdict": verdict_v3,
                           "expected": test["expected"], "elapsed": r3["elapsed"],
                           "exploitability": v3_exploit, "severity": severity_v3,
                           "category": test["id"][:2]})
        
        # Add delay between tests to avoid rate limiting
        if PROVIDER == "Groq" and idx < len(TEST_CASES) - 1:
            time.sleep(delay_between_tests)
    
    # Final report
    total = len(TEST_CASES)
    fp_cases = [t for t in TEST_CASES if t["expected"] == "ACCEPT"]
    tp_cases = [t for t in TEST_CASES if t["expected"] == "REJECT"]
    edge_cases = [t for t in TEST_CASES if t["id"].startswith("E")]
    
    def accuracy(results, filter_ids=None):
        subset = results if not filter_ids else [r for r in results if r["id"] in filter_ids]
        if not subset: return 0
        return 100 * sum(1 for r in subset if r["correct"]) / len(subset)
    
    fp_ids = [t["id"] for t in fp_cases]
    tp_ids = [t["id"] for t in tp_cases]
    e_ids = [t["id"] for t in edge_cases]
    
    print(f"{'='*70}")
    print(f"FINAL RESULTS")
    print(f"{'='*70}")
    print(f"\n{'Metric':<40} {'V1 Legacy':>12} {'V2 Full':>12} {'V2 Fast':>12}")
    print(f"{'-'*76}")
    print(f"{'Overall accuracy':<40} {accuracy(results_v1):>11.0f}% {accuracy(results_v2):>11.0f}% {accuracy(results_v3):>11.0f}%")
    print(f"{'False positive accuracy (traps)':<40} {accuracy(results_v1, fp_ids):>11.0f}% {accuracy(results_v2, fp_ids):>11.0f}% {accuracy(results_v3, fp_ids):>11.0f}%")
    print(f"{'Violation detection (must flag)':<40} {accuracy(results_v1, tp_ids):>11.0f}% {accuracy(results_v2, tp_ids):>11.0f}% {accuracy(results_v3, tp_ids):>11.0f}%")
    print(f"{'Edge case accuracy':<40} {accuracy(results_v1, e_ids):>11.0f}% {accuracy(results_v2, e_ids):>11.0f}% {accuracy(results_v3, e_ids):>11.0f}%")
    print(f"{'Average response time':<40} {statistics.mean(r['elapsed'] for r in results_v1):>10.1f}s {statistics.mean(r['elapsed'] for r in results_v2):>10.1f}s {statistics.mean(r['elapsed'] for r in results_v3):>10.1f}s")
    
    v1_correct = sum(1 for r in results_v1 if r["correct"])
    v2_correct = sum(1 for r in results_v2 if r["correct"])
    v3_correct = sum(1 for r in results_v3 if r["correct"])
    
    v1_wins = sum(1 for r1, r2, r3 in zip(results_v1, results_v2, results_v3) if r1["correct"] and not r2["correct"] and not r3["correct"])
    v2_wins = sum(1 for r1, r2, r3 in zip(results_v1, results_v2, results_v3) if r2["correct"] and not r1["correct"])
    v3_wins = sum(1 for r1, r2, r3 in zip(results_v1, results_v2, results_v3) if r3["correct"] and not r1["correct"] and not r2["correct"])
    
    print(f"\n{'='*70}")
    print(f"VERDICT")
    print(f"{'='*70}")
    print(f"\n  V1 Legacy:      {v1_correct}/{total} correct | wins over V2/V2F on {v1_wins} cases")
    print(f"  V2 Full:        {v2_correct}/{total} correct | wins over V1 on {v2_wins} cases")
    print(f"  V2 Fast:        {v3_correct}/{total} correct | unique wins on {v3_wins} cases")
    
    best_accuracy = max(v1_correct, v2_correct, v3_correct)
    best_speed = min(statistics.mean(r['elapsed'] for r in results_v1),
                     statistics.mean(r['elapsed'] for r in results_v2),
                     statistics.mean(r['elapsed'] for r in results_v3))
    
    if v3_correct >= v2_correct and statistics.mean(r['elapsed'] for r in results_v3) < statistics.mean(r['elapsed'] for r in results_v2):
        print(f"\n  🏆 V2 FAST WINS — Same accuracy as V2 Full but faster")
        print(f"  Speed improvement: {((statistics.mean(r['elapsed'] for r in results_v2) - statistics.mean(r['elapsed'] for r in results_v3)) / statistics.mean(r['elapsed'] for r in results_v2) * 100):.0f}% faster than V2 Full")
    elif v2_correct > v1_correct:
        improvement = v2_correct - v1_correct
        print(f"\n  🏆 V2 FULL WINS — {improvement} more correct answers than V1")
        print(f"  V2 is better at reducing false positives while catching real violations")
    elif v1_correct > v2_correct:
        print(f"\n  ⚠️  V1 outperforms V2 — V2 constraints may be too conservative")
    else:
        print(f"\n  🤝 TIE — different strengths on different case types")
    
    print(f"\n{'='*70}\n")

# Add this as an alternative entry point
def run_blind_spot_debug():
    blind_spot_ids = ["BS1a", "BS1b", "BS2a", "BS2b", "BS3a", "BS3b"]
    global TEST_CASES
    TEST_CASES = [t for t in TEST_CASES if t["id"] in blind_spot_ids]
    run_benchmark()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        run_blind_spot_debug()
    else:
        run_benchmark()
