import subprocess
import os
import sys
import shutil

def check_gpu():
    print("--- TREPAN GPU DIAGNOSTIC TOOL ---")
    print("=" * 40)
    
    # 1. System Info
    print(f"OS: {sys.platform}")
    print(f"Python: {sys.version.split()[0]}")
    
    # 2. Check nvidia-smi
    print("\n[INFO] Checking NVIDIA Drivers (nvidia-smi):")
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            res = subprocess.run([smi], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                print("[OK] nvidia-smi is reachable.")
                # Print GPU Name and Usage
                for line in res.stdout.splitlines():
                    if "GeForce" in line or "NVIDIA" in line or "RTX" in line:
                        print(f"   Detected: {line.strip()}")
            else:
                print("[FAIL] nvidia-smi returned error code.")
        except Exception as e:
            print(f"[ERROR] Error running nvidia-smi: {e}")
    else:
        print("[FAIL] nvidia-smi NOT FOUND in PATH.")

    # 3. Check for CUDA via PyTorch or others if installed
    print("\n[INFO] Checking Library Support:")
    try:
        import torch
        print(f"[OK] PyTorch version: {torch.__version__}")
        print(f"   CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"   Current Device: {torch.cuda.get_device_name(0)}")
            print(f"   Device Count: {torch.cuda.device_count()}")
    except ImportError:
        print("[WARN] PyTorch not installed in this venv.")

    try:
        import onnxruntime as ort
        print(f"[OK] ONNX Runtime version: {ort.get_version_string()}")
        providers = ort.get_available_providers()
        print(f"   Available Providers: {providers}")
        if "CUDAExecutionProvider" in providers:
            print("   [OK] CUDA Execution Provider IS available.")
        else:
            print("   [FAIL] CUDA Execution Provider NOT found (CPU only).")
    except ImportError:
        print("[WARN] ONNX Runtime not installed in this venv.")

    # 4. Check Ollama Env
    print("\n[INFO] Checking Ollama Environment Variables:")
    env_vars = ["OLLAMA_HOST", "OLLAMA_MODELS", "CUDA_VISIBLE_DEVICES", "OLLAMA_LLM_LIBRARY"]
    for var in env_vars:
        print(f"   {var}: {os.environ.get(var, 'NOT SET')}")

    # 5. Check if Ollama is listening
    print("\n[INFO] Checking Ollama Service Status:")
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as resp:
            if resp.status == 200:
                print("[OK] Ollama Service is RUNNING on localhost:11434")
    except:
        print("[FAIL] Ollama Service is NOT REACHABLE on localhost:11434")

if __name__ == "__main__":
    check_gpu()
