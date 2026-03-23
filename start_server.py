#!/usr/bin/env python3
"""
Trepan — Universal Server Wrapper (BETA)
This script prepares the environment and starts the Trepan backend.
Designed for beta users without Conda/complex setups.
"""

import subprocess
import sys
import os
import shutil
import time
import requests

# Configuration
MODEL_NAME = "llama3.1:8b"
HOST = "0.0.0.0"
PORT = "8001"
OLLAMA_URL = "http://localhost:11434"

def print_header(text):
    print(f"\n{'='*60}")
    print(f" {text}")
    print(f"{'='*60}\n")

def check_ollama_installed():
    """Check if Ollama binary is in PATH."""
    if shutil.which("ollama") is None:
        print("[ERROR] Ollama is not installed.")
        print("   Please download and install it from: https://ollama.com")
        print("   After installing, restart your terminal and run this script again.")
        return False
    print("[OK] Ollama installation found.")
    return True

def kill_ollama_processes():
    """Kill all running Ollama processes."""
    print("[INFO] Killing all Ollama processes...")
    try:
        if sys.platform == "win32":
            # Windows: Use taskkill
            subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], 
                         capture_output=True, timeout=10)
            subprocess.run(["taskkill", "/F", "/IM", "ollama_llama_server.exe"], 
                         capture_output=True, timeout=10)
            print("[OK] Ollama processes killed (Windows)")
        else:
            # Unix-like: Use pkill
            subprocess.run(["pkill", "-9", "ollama"], 
                         capture_output=True, timeout=10)
            print("[OK] Ollama processes killed (Unix)")
        
        # Wait a moment for processes to fully terminate
        time.sleep(2)
        return True
    except Exception as e:
        print(f"[WARN] Could not kill Ollama processes: {e}")
        print("   You may need to kill them manually")
        return False

def ensure_ollama_running():
    """Ensure Ollama service is running, auto-starting it if needed."""
    # Check if already running
    try:
        resp = requests.get(OLLAMA_URL, timeout=5)
        if resp.status_code == 200:
            print("[OK] Ollama service is already running.")
            return True
    except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, requests.exceptions.Timeout):
        pass

    # Not running — attempt to start it automatically
    print("[INFO] Ollama is not running. Attempting to start 'ollama serve' automatically...")
    try:
        # Start as a detached background process so it outlives this script
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True

        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy(),  # Pass the optimized env to Ollama process
            **kwargs
        )
    except FileNotFoundError:
        print("[ERROR] 'ollama' command not found. Is Ollama installed and in your PATH?")
        print("   Download it from: https://ollama.com")
        return False
    
    # Wait up to 45 seconds for Ollama to become ready (Windows can be slow)
    print("[INFO] Waiting for Ollama to start (up to 45s)", end="", flush=True)
    for i in range(45):
        time.sleep(1)
        print(".", end="", flush=True)
        try:
            resp = requests.get(OLLAMA_URL, timeout=5)
            if resp.status_code == 200:
                print(f"\n[OK] Ollama started successfully after {i+1} seconds.")
                return True
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, requests.exceptions.Timeout):
            pass

    print("\n[ERROR] Timed out waiting for Ollama to start (45s).")
    print("   Try running 'ollama serve' manually in another terminal, then re-run start_server.py.")
    return False

def pull_model():
    """Ensure the required LLM is downloaded by checking the local registry first."""
    print(f"[INFO] Checking local registry for model: {MODEL_NAME}...")
    
    # First, verify Ollama is still responsive
    try:
        print("[INFO] Verifying Ollama service is responsive...")
        resp = requests.get(OLLAMA_URL, timeout=5)
        if resp.status_code != 200:
            print(f"[WARN] Ollama returned status {resp.status_code}")
    except Exception as e:
        print(f"\n[ERROR] Ollama service is not responding!")
        print(f"   Details: {e}")
        print("\n[INFO] Attempting automatic recovery...")
        
        # Kill stuck Ollama processes
        kill_ollama_processes()
        
        # Try to restart Ollama
        print("[INFO] Restarting Ollama service...")
        if not ensure_ollama_running():
            print("\n[ERROR] Failed to restart Ollama automatically.")
            print("   Manual steps:")
            print("   1. Open Task Manager and kill all 'ollama' processes")
            print("   2. Open a new terminal and run: ollama serve")
            print("   3. Re-run this script")
            return False
        
        print("[OK] Ollama restarted successfully!")
        # Continue with model check after restart
    
    try:
        # Check local registry using subprocess for speed and reliability
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True, timeout=10)
        
        # Parse output properly to match model names (first column)
        installed_models = []
        for line in res.stdout.splitlines()[1:]:  # Skip header
            if line.strip():
                installed_models.append(line.split()[0])
                
        if MODEL_NAME in installed_models or f"{MODEL_NAME}:latest" in installed_models:
            print(f"[OK] Model {MODEL_NAME} already exists. Starting server...")
            return True
        
        # Only if not found, proceed to pull the base model
        BASE_MODEL = "llama3.1:8b"
        print(f"[INFO] Model {MODEL_NAME} not found. Pulling base model {BASE_MODEL}... (This may take a few minutes)")
        subprocess.run(["ollama", "pull", BASE_MODEL], check=True)
        print(f"[OK] Base model {BASE_MODEL} pulled successfully.")
        print(f"[WARN] Note: You may need to build the custom '{MODEL_NAME}' model. Using base model for now.")
        return True
    except FileNotFoundError:
        print("\n[ERROR] 'ollama' command not found.")
        print("   Solution:")
        print("   1. Install Ollama from: https://ollama.com/download")
        print("   2. Make sure Ollama is in your PATH")
        print("   3. Restart your terminal after installation")
        return False
    except subprocess.TimeoutExpired:
        print("\n[ERROR] 'ollama list' command timed out (10s)")
        print("   Ollama appears to be stuck or crashed.")
        print("\n[INFO] Attempting automatic recovery...")
        
        # Kill stuck Ollama processes
        kill_ollama_processes()
        
        # Try to restart Ollama
        print("[INFO] Restarting Ollama service...")
        if not ensure_ollama_running():
            print("\n[ERROR] Failed to restart Ollama automatically.")
            print("   Manual steps:")
            print("   1. Open Task Manager and kill all 'ollama' processes")
            print("   2. Open a new terminal and run: ollama serve")
            print("   3. Re-run this script")
            return False
        
        print("[OK] Ollama restarted successfully!")
        print("[INFO] Retrying model check...")
        
        # Retry the model check after restart
        try:
            res = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True, timeout=10)
            installed_models = []
            for line in res.stdout.splitlines()[1:]:
                if line.strip():
                    installed_models.append(line.split()[0])
            
            if MODEL_NAME in installed_models or f"{MODEL_NAME}:latest" in installed_models:
                print(f"[OK] Model {MODEL_NAME} found after restart.")
                return True
            else:
                print(f"[INFO] Pulling model {MODEL_NAME}...")
                subprocess.run(["ollama", "pull", MODEL_NAME], check=True)
                return True
        except Exception as retry_error:
            print(f"[ERROR] Retry failed: {retry_error}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Ollama command failed (exit code {e.returncode})")
        
        # Check for specific error patterns
        error_output = (e.stderr or "") + (e.stdout or "")
        is_eof_error = "EOF" in error_output or "connection refused" in error_output.lower()
        
        if e.stderr:
            print(f"Error output: {e.stderr.strip()}")
        if e.stdout:
            print(f"Standard output: {e.stdout.strip()}")
        
        if is_eof_error:
            print("\n[INFO] Detected Ollama connection error. Attempting automatic recovery...")
            
            # Kill stuck Ollama processes
            kill_ollama_processes()
            
            # Try to restart Ollama
            print("[INFO] Restarting Ollama service...")
            if not ensure_ollama_running():
                print("\n[ERROR] Failed to restart Ollama automatically.")
                print("   Manual steps:")
                print("   1. Open Task Manager and kill all 'ollama' processes")
                print("   2. Open a new terminal and run: ollama serve")
                print("   3. Re-run this script")
                return False
            
            print("[OK] Ollama restarted successfully!")
            print("[INFO] Retrying model check...")
            
            # Retry the model check after restart
            try:
                res = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True, timeout=10)
                installed_models = []
                for line in res.stdout.splitlines()[1:]:
                    if line.strip():
                        installed_models.append(line.split()[0])
                
                if MODEL_NAME in installed_models or f"{MODEL_NAME}:latest" in installed_models:
                    print(f"[OK] Model {MODEL_NAME} found after restart.")
                    return True
                else:
                    print(f"[INFO] Pulling model {MODEL_NAME}...")
                    subprocess.run(["ollama", "pull", MODEL_NAME], check=True)
                    return True
            except Exception as retry_error:
                print(f"[ERROR] Retry failed: {retry_error}")
                return False
        else:
            print("\nCommon causes:")
            print("1. Ollama service crashed after starting")
            print("   -> Check if 'ollama serve' is still running")
            print("2. Ollama is stuck or unresponsive")
            print("   -> Kill Ollama processes and restart")
            print("3. Permission issues")
            print("   -> Try running as administrator/sudo")
            print("\nQuick fix:")
            print("1. Open Task Manager (Windows) or Activity Monitor (Mac)")
            print("2. Kill all 'ollama' processes")
            print("3. Open a new terminal and run: ollama serve")
            print("4. Re-run this script")
            return False
    except Exception as e:
        print(f"[ERROR] Unexpected error during model check: {e}")
        return False

def start_server():
    """Launch the FastAPI server using Uvicorn with optimized settings."""
    print_header(f"Starting Trepan Server on {HOST}:{PORT}")
    
    # Performance Optimization: Single worker, no access log for speed
    server_cmd = [
        sys.executable, "-m", "uvicorn", 
        "trepan_server.server:app", 
        "--host", HOST, 
        "--port", PORT,
        "--workers", "1",
        "--no-access-log"
    ]
    
    print(f"Executing: {' '.join(server_cmd)}")
    try:
        subprocess.run(server_cmd)
    except KeyboardInterrupt:
        print("\n[INFO] Server stopped by user.")
    except Exception as e:
        print(f"[ERROR] Error starting server: {e}")

def main():
    print_header("TREPAN BACKEND BOOTSTRAPPER")
    
    # GPU optimization — must be set before Ollama starts
    os.environ["OLLAMA_NUM_PARALLEL"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    os.environ["OLLAMA_GPU_OVERHEAD"] = "0"
    print("[INFO] GPU optimization flags set")
    
    if not check_ollama_installed():
        sys.exit(1)
    
    if not ensure_ollama_running():
        sys.exit(1)
        
    if not pull_model():
        sys.exit(1)
        
    start_server()

if __name__ == "__main__":
    main()
