#!/usr/bin/env python3
"""
TREPAN FULL SYSTEM DIAGNOSTIC
No code changes - pure investigation
"""

import sys
import os
import json
import socket
import subprocess
from pathlib import Path

print("=" * 80)
print("🔍 TREPAN FULL SYSTEM DIAGNOSTIC")
print("=" * 80)
print()

# ============================================================================
# SECTION 1: ENVIRONMENT CHECK
# ============================================================================
print("📋 SECTION 1: ENVIRONMENT CHECK")
print("-" * 80)

print(f"Python Version: {sys.version}")
print(f"Python Executable: {sys.executable}")
print(f"Current Working Directory: {os.getcwd()}")
print(f"Platform: {sys.platform}")

# Check if running in WSL
is_wsl = os.path.exists('/proc/version') and 'microsoft' in open('/proc/version').read().lower()
print(f"Running in WSL: {is_wsl}")

if is_wsl:
    try:
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        wsl_ip = result.stdout.strip().split()[0] if result.stdout else "Unknown"
        print(f"WSL IP Address: {wsl_ip}")
    except Exception as e:
        print(f"Could not get WSL IP: {e}")

print()

# ============================================================================
# SECTION 2: PORT AVAILABILITY CHECK
# ============================================================================
print("📋 SECTION 2: PORT AVAILABILITY CHECK")
print("-" * 80)

def check_port(host, port):
    """Check if a port is listening"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        return False

# Check common ports
ports_to_check = [8000, 8001, 11434]
hosts_to_check = ['127.0.0.1', '0.0.0.0']

if is_wsl:
    try:
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        wsl_ip = result.stdout.strip().split()[0] if result.stdout else None
        if wsl_ip:
            hosts_to_check.append(wsl_ip)
    except:
        pass

for port in ports_to_check:
    print(f"\nPort {port}:")
    for host in hosts_to_check:
        is_listening = check_port(host, port)
        status = "✅ LISTENING" if is_listening else "❌ NOT LISTENING"
        print(f"  {host}:{port} - {status}")

print()

# ============================================================================
# SECTION 3: HTTP ENDPOINT CHECK
# ============================================================================
print("📋 SECTION 3: HTTP ENDPOINT CHECK")
print("-" * 80)

try:
    import requests
    
    urls_to_test = [
        "http://127.0.0.1:8000/health",
        "http://127.0.0.1:8001/health",
        "http://localhost:8000/health",
        "http://localhost:8001/health",
    ]
    
    if is_wsl and wsl_ip:
        urls_to_test.extend([
            f"http://{wsl_ip}:8000/health",
            f"http://{wsl_ip}:8001/health",
        ])
    
    for url in urls_to_test:
        try:
            print(f"\nTesting: {url}")
            response = requests.get(url, timeout=3)
            print(f"  Status Code: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            if response.status_code == 200:
                print(f"  ✅ SERVER RESPONDING")
        except requests.exceptions.ConnectionError as e:
            print(f"  ❌ CONNECTION REFUSED")
        except requests.exceptions.Timeout:
            print(f"  ❌ TIMEOUT")
        except Exception as e:
            print(f"  ❌ ERROR: {type(e).__name__}: {e}")
            
except ImportError:
    print("⚠️ requests library not installed - skipping HTTP checks")
    print("Install with: pip install requests")

print()

# ============================================================================
# SECTION 4: VS CODE SETTINGS CHECK
# ============================================================================
print("📋 SECTION 4: VS CODE SETTINGS CHECK")
print("-" * 80)

# Check for VS Code settings files
vscode_settings_locations = [
    Path.home() / ".vscode" / "settings.json",
    Path.home() / "AppData" / "Roaming" / "Code" / "User" / "settings.json",  # Windows
    Path.home() / ".config" / "Code" / "User" / "settings.json",  # Linux
    Path(os.getcwd()) / ".vscode" / "settings.json",  # Workspace
]

print("Searching for VS Code settings files:")
for location in vscode_settings_locations:
    if location.exists():
        print(f"\n✅ Found: {location}")
        try:
            with open(location, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                
            # Look for Trepan settings
            trepan_settings = {k: v for k, v in settings.items() if 'trepan' in k.lower()}
            if trepan_settings:
                print("  Trepan Settings:")
                for key, value in trepan_settings.items():
                    print(f"    {key}: {value}")
            else:
                print("  ⚠️ No Trepan settings found in this file")
        except Exception as e:
            print(f"  ❌ Could not read settings: {e}")
    else:
        print(f"❌ Not found: {location}")

print()

# ============================================================================
# SECTION 5: TREPAN SERVER PROCESS CHECK
# ============================================================================
print("📋 SECTION 5: TREPAN SERVER PROCESS CHECK")
print("-" * 80)

try:
    if sys.platform == 'win32':
        # Windows
        result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        print("Processes listening on ports 8000-8001:")
        for line in lines:
            if ':8000' in line or ':8001' in line:
                print(f"  {line.strip()}")
    else:
        # Linux/WSL
        result = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        print("Processes listening on ports 8000-8001:")
        for line in lines:
            if ':8000' in line or ':8001' in line:
                print(f"  {line.strip()}")
                
        # Also check with lsof
        try:
            result = subprocess.run(['lsof', '-i', ':8000'], capture_output=True, text=True)
            if result.stdout:
                print("\nlsof output for port 8000:")
                print(result.stdout)
                
            result = subprocess.run(['lsof', '-i', ':8001'], capture_output=True, text=True)
            if result.stdout:
                print("\nlsof output for port 8001:")
                print(result.stdout)
        except FileNotFoundError:
            print("  (lsof not available)")
            
except Exception as e:
    print(f"❌ Could not check processes: {e}")

print()

# ============================================================================
# SECTION 6: TREPAN PROJECT STRUCTURE CHECK
# ============================================================================
print("📋 SECTION 6: TREPAN PROJECT STRUCTURE CHECK")
print("-" * 80)

required_files = [
    "trepan_server/server.py",
    "trepan_server/prompt_builder.py",
    "trepan_server/response_parser.py",
    "extension/extension.js",
    "extension/package.json",
    "start_server.py",
]

print("Checking required files:")
for file_path in required_files:
    path = Path(file_path)
    if path.exists():
        size = path.stat().st_size
        print(f"  ✅ {file_path} ({size:,} bytes)")
    else:
        print(f"  ❌ MISSING: {file_path}")

print()

# Check .trepan folder
trepan_test_zone = Path.home() / "Documents" / "Projects" / "Trepan_Test_Zone" / ".trepan"
if trepan_test_zone.exists():
    print(f"✅ Found .trepan folder: {trepan_test_zone}")
    pillar_files = [
        "golden_state.md",
        "system_rules.md",
        "done_tasks.md",
        "pending_tasks.md",
        "history_phases.md",
        "problems_and_resolutions.md",
    ]
    print("  Pillar files:")
    for pillar in pillar_files:
        pillar_path = trepan_test_zone / pillar
        if pillar_path.exists():
            size = pillar_path.stat().st_size
            print(f"    ✅ {pillar} ({size:,} bytes)")
        else:
            print(f"    ❌ MISSING: {pillar}")
else:
    print(f"❌ .trepan folder not found: {trepan_test_zone}")

print()

# ============================================================================
# SECTION 7: OLLAMA CHECK
# ============================================================================
print("📋 SECTION 7: OLLAMA CHECK")
print("-" * 80)

try:
    import requests
    
    ollama_url = "http://localhost:11434/api/tags"
    print(f"Testing Ollama at: {ollama_url}")
    
    try:
        response = requests.get(ollama_url, timeout=3)
        print(f"  Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])
            print(f"  ✅ Ollama is running")
            print(f"  Available models: {len(models)}")
            for model in models:
                print(f"    - {model.get('name', 'unknown')}")
                
            # Check for llama3.1:8b
            has_llama = any('llama3.1' in m.get('name', '') for m in models)
            if has_llama:
                print(f"  ✅ llama3.1:8b is available")
            else:
                print(f"  ⚠️ llama3.1:8b NOT found - run: ollama pull llama3.1:8b")
        else:
            print(f"  ❌ Unexpected status code")
    except requests.exceptions.ConnectionError:
        print(f"  ❌ CONNECTION REFUSED - Ollama not running")
        print(f"  Start with: ollama serve")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        
except ImportError:
    print("⚠️ requests library not installed - skipping Ollama check")

print()

# ============================================================================
# SECTION 8: EXTENSION PACKAGE.JSON CHECK
# ============================================================================
print("📋 SECTION 8: EXTENSION PACKAGE.JSON CHECK")
print("-" * 80)

package_json_path = Path("extension/package.json")
if package_json_path.exists():
    print(f"✅ Found: {package_json_path}")
    try:
        with open(package_json_path, 'r', encoding='utf-8') as f:
            package_data = json.load(f)
        
        print(f"  Extension Name: {package_data.get('name', 'unknown')}")
        print(f"  Version: {package_data.get('version', 'unknown')}")
        print(f"  Display Name: {package_data.get('displayName', 'unknown')}")
        
        # Check configuration
        config = package_data.get('contributes', {}).get('configuration', {}).get('properties', {})
        print("\n  Configuration Properties:")
        for key, value in config.items():
            default = value.get('default', 'none')
            print(f"    {key}: {default}")
            
    except Exception as e:
        print(f"  ❌ Could not read package.json: {e}")
else:
    print(f"❌ NOT FOUND: {package_json_path}")

print()

# ============================================================================
# SUMMARY
# ============================================================================
print("=" * 80)
print("🎯 DIAGNOSTIC SUMMARY")
print("=" * 80)
print()
print("Run this diagnostic and share the output to identify the issue.")
print()
print("Key things to check:")
print("1. Is a server process listening on port 8000 or 8001?")
print("2. Does the HTTP /health endpoint respond?")
print("3. What URL is configured in VS Code settings?")
print("4. Is Ollama running and does it have llama3.1:8b?")
print("5. Are all required files present?")
print()
print("=" * 80)
