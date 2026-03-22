#!/usr/bin/env python3
"""
🛡️ Trepan — Universal Server Wrapper (BETA)
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
        print("❌ Error: Ollama is not installed.")
        print("   Please download and install it from: https://ollama.com")
        print("   After installing, restart your terminal and run this script again.")
        return False
    print("✅ Ollama installation found.")
    return True

def ensure_ollama_running():
    """Ensure Ollama service is running, auto-starting it if needed."""
    # Check if already running
    try:
        resp = requests.get(OLLAMA_URL, timeout=2)
        if resp.status_code == 200 and "Ollama is running" in resp.text:
            print("✅ Ollama service is already running.")
            return True
    except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
        pass

    # Not running — attempt to start it automatically
    print("⚙️  Ollama is not running. Attempting to start 'ollama serve' automatically...")
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
        print("❌ Error: 'ollama' command not found. Is Ollama installed and in your PATH?")
        print("   Download it from: https://ollama.com")
        return False
    # Wait up to 30 seconds for Ollama to become ready
    print("⏳ Waiting for Ollama to start", end="", flush=True)
    for _ in range(30):
        time.sleep(1)
        print(".", end="", flush=True)
        try:
            resp = requests.get(OLLAMA_URL, timeout=2)
            if resp.status_code == 200 and "Ollama is running" in resp.text:
                print("\n✅ Ollama started successfully.")
                return True
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
            pass

    print("\n❌ Timed out waiting for Ollama to start (30s).")
    print("   Try running 'ollama serve' manually in another terminal, then re-run start_server.py.")
    return False

def pull_model():
    """Ensure the required LLM is downloaded by checking the local registry first."""
    print(f"📦 Checking local registry for model: {MODEL_NAME}...")
    try:
        # Check local registry using subprocess for speed and reliability
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
        
        # Parse output properly to match model names (first column)
        installed_models = []
        for line in res.stdout.splitlines()[1:]:  # Skip header
            if line.strip():
                installed_models.append(line.split()[0])
                
        if MODEL_NAME in installed_models or f"{MODEL_NAME}:latest" in installed_models:
            print(f"✅ Model {MODEL_NAME} already exists. Starting server...")
            return True
        
        # Only if not found, proceed to pull the base model
        BASE_MODEL = "llama3.1:8b"
        print(f"⬇️  Model {MODEL_NAME} not found. Pulling base model {BASE_MODEL}... (This may take a few minutes)")
        subprocess.run(["ollama", "pull", BASE_MODEL], check=True)
        print(f"✅ Base model {BASE_MODEL} pulled successfully.")
        print(f"⚠️ Note: You may need to build the custom '{MODEL_NAME}' model. Using base model for now.")
        return True
    except FileNotFoundError:
        print("❌ Error: 'ollama' command not found. Is it in your PATH?")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Error checking/pulling model: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during model check: {e}")
        return False

def start_server():
    """Launch the FastAPI server using Uvicorn with optimized settings."""
    print_header(f"🚀 Starting Trepan Server on {HOST}:{PORT}")
    
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
        print("\n🛑 Server stopped by user.")
    except Exception as e:
        print(f"❌ Error starting server: {e}")

def main():
    print_header("🛡️  TREPAN BACKEND BOOTSTRAPPER")
    
    # GPU optimization — must be set before Ollama starts
    os.environ["OLLAMA_NUM_PARALLEL"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    os.environ["OLLAMA_GPU_OVERHEAD"] = "0"
    print("🎮 GPU optimization flags set")
    
    if not check_ollama_installed():
        sys.exit(1)
    
    if not ensure_ollama_running():
        sys.exit(1)
        
    if not pull_model():
        sys.exit(1)
        
    start_server()

if __name__ == "__main__":
    main()
