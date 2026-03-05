#!/usr/bin/env python3
"""
🛡️ Trepan Gatekeeper — Quick Server Launcher
Convenience script that starts the FastAPI server from the project root.

Usage:
    python start_server.py
    python start_server.py --port 8001  # use a custom port
    python start_server.py --reload     # dev mode with auto-reload
    python start_server.py --skip-sklearn  # skip sklearn checks
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

def check_port_available(host: str, port: int) -> bool:
    """Check if a port is available for binding."""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result != 0  # Port is available if connection fails
    except Exception as e:
        print(f"⚠️  Could not check port {port}: {e}")
        return True  # Assume available if check fails

def check_dependencies(skip_sklearn: bool = False):
    """Check and report on critical dependencies."""
    print("🔍 Checking dependencies...\n")

    # Hard requirements — server won't start without these
    hard_deps   = {"fastapi": "FastAPI", "uvicorn": "Uvicorn (server)"}
    # Soft requirements — model loading will fail but server still starts
    soft_deps   = {"transformers": "Transformers", "torch": "PyTorch", "peft": "PEFT (adapters)"}

    if not skip_sklearn:
        soft_deps["sklearn"] = "scikit-learn"

    missing_hard = []
    for module, name in {**hard_deps, **soft_deps}.items():
        try:
            __import__(module)
            print(f"  ✅ {name}")
        except Exception as e:
            is_hard = module in hard_deps
            icon    = "❌" if is_hard else "⚠️ "
            print(f"  {icon} {name}: {str(e)[:80]}")
            if is_hard:
                missing_hard.append(name)

    if missing_hard:
        print(f"\n❌ Missing hard requirements: {', '.join(missing_hard)}")
        print("   pip install " + " ".join(m.split()[0].lower() for m in missing_hard))
        return False

    print("\n✅ Core server deps OK — soft failures handled at runtime.\n")
    return True

def ensure_ollama_running():
    """Nuclear Restart for Ollama to ensure clean GPU detection."""
    import urllib.request
    import urllib.error
    
    ollama_url = "http://localhost:11434/api/tags"
    ollama_bin = "/usr/local/bin/ollama" if not sys.platform.startswith("win") else "ollama"
    
    # SERVICE CONFLICT RESOLVER (Linux/WSL only)
    if not sys.platform.startswith("win"):
        try:
            # Check if ollama service is active
            res = subprocess.run(["sudo", "systemctl", "is-active", "ollama"], capture_output=True, text=True)
            if res.stdout.strip() == "active":
                print("🛑 Detected ACTIVE Ollama service. Stopping it to prevent CPU pinning...")
                subprocess.run(["sudo", "systemctl", "stop", "ollama"], check=True)
                time.sleep(2)
        except Exception as e:
            print(f"⚠️ Service check failed: {e}")

    # NUCLEAR OPTION: Kill any existing Ollama processes to ensure clean GPU detection
    print("🧨 Performing Nuclear Ollama Restart for GPU detection...")
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/F", "/IM", "ollama.exe", "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["taskkill", "/F", "/IM", "ollama_llama_server.exe", "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)
        else:
            subprocess.run(["pkill", "-9", "ollama"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
    except:
        pass

    # Set EXPLICIT GPU and Network environment variables
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "0.0.0.0:11434"
    env["OLLAMA_ORIGINS"] = "*"
    env["CUDA_VISIBLE_DEVICES"] = "0"
    env["OLLAMA_GPU_OVERHEAD"] = "512MiB"
    # Force CUDA if available
    if sys.platform.startswith("win"):
        env["OLLAMA_LLM_LIBRARY"] = "cuda"
    
    # Ollama is not running (or just killed) — start it
    print(f"⚠️  Starting '{ollama_bin} serve' in background (HOST: {env['OLLAMA_HOST']})...")
    try:
        if sys.platform.startswith("win"):
            # Windows: use CREATE_NEW_PROCESS_GROUP to detach
            ollama_proc = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            )
        else:
            # Linux/WSL: use nohup-style background
            ollama_proc = subprocess.Popen(
                [ollama_bin, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
        
        print(f"   Ollama PID: {ollama_proc.pid}")
        
        # Wait for Ollama to become responsive (up to 20 seconds)
        for i in range(20):
            time.sleep(1)
            try:
                req = urllib.request.Request(ollama_url, method="GET")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        print(f"✅ Ollama is now running with GPU Support (took {i+1}s)")
                        return True
            except (urllib.error.URLError, urllib.error.HTTPError, OSError):
                print(f"   Waiting for Ollama GPU initialization... ({i+1}/20s)")
        
        print("⚠️  Ollama started but not responding. Might be compiling shaders or model loading.")
        return False
        
    except FileNotFoundError:
        print("❌ 'ollama' command not found. Please install Ollama: https://ollama.com")
        print("   The server will still start, but LLM evaluation will fail.")
        return False
    except Exception as e:
        print(f"❌ Failed to start Ollama: {e}")
        return False

def check_gpu_status():
    """Diagnostic helper to see if GPU is visible to Python."""
    import shutil
    import subprocess
    import os
    
    print("\n🔍 GPU DIAGNOSTICS:")
    
    # 1. Check for nvidia-smi
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            res = subprocess.run([smi], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                print("✅ NVIDIA GPU Detected (nvidia-smi exists and responds)")
                # Print just the first few lines of smi for signal
                print("\n".join(res.stdout.splitlines()[:10]))
            else:
                print("⚠️  nvidia-smi failed. Drivers might be missing or crashed.")
        except Exception as e:
            print(f"⚠️  Error running nvidia-smi: {e}")
    else:
        print("❌ nvidia-smi NOT FOUND. If you have an NVIDIA GPU, ensure drivers are installed.")

    # 2. Check for relevant Environment Variables
    gpu_vars = ["CUDA_VISIBLE_DEVICES", "OLLAMA_HOST", "OLLAMA_MODELS", "PATH"]
    print("\n📋 RELEVANT ENVIRONMENT:")
    for v in gpu_vars:
        val = os.environ.get(v, "NOT_SET")
        # Truncate PATH if too long
        if v == "PATH" and len(val) > 100:
            val = val[:100] + "..."
        print(f"   {v}: {val}")
    print("=" * 30 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Start the Trepan Gatekeeper server")
    parser.add_argument("--port",            type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--host",            default="127.0.0.1",   help="Host (default: 127.0.0.1)")
    parser.add_argument("--reload",          action="store_true",   help="Dev mode (auto-reload)")
    parser.add_argument("--skip-sklearn",    action="store_true",   help="Skip sklearn check")
    parser.add_argument("--check-only",      action="store_true",   help="Only check deps, don't start")
    args = parser.parse_args()

    # ─── GPU & Ollama Check ───
    check_gpu_status()
    ensure_ollama_running()

    # TRANSPARENCY FIX: Check port availability before starting
    print(f"🔍 Checking if port {args.port} is available on {args.host}...")
    if not check_port_available(args.host, args.port):
        print(f"❌ Port {args.port} is already in use!")
        print(f"   Another process is listening on {args.host}:{args.port}")
        print(f"   Kill the process or use a different port with --port")
        
        # Try to identify what's using the port
        try:
            if sys.platform.startswith("linux"):
                result = subprocess.run(["lsof", "-i", f":{args.port}"], 
                                      capture_output=True, text=True)
                if result.stdout:
                    print(f"   Process using port {args.port}:")
                    print(f"   {result.stdout}")
            elif sys.platform.startswith("win"):
                result = subprocess.run(["netstat", "-ano", "|", "findstr", f":{args.port}"], 
                                      shell=True, capture_output=True, text=True)
                if result.stdout:
                    print(f"   Process using port {args.port}:")
                    print(f"   {result.stdout}")
        except Exception as e:
            print(f"   Could not identify process: {e}")
        
        sys.exit(1)
    else:
        print(f"✅ Port {args.port} is available")

    # Check dependencies
    if not check_dependencies(skip_sklearn=args.skip_sklearn):
        sys.exit(1)
    
    if args.check_only:
        print("✅ All checks passed. Ready to start server!")
        return

    project_root = Path(__file__).parent

    cmd = [
        sys.executable, "-m", "uvicorn",
        "trepan_server.server:app",
        "--host", args.host,
        "--port", str(args.port),
        "--log-level", "info",
    ]

    if args.reload:
        cmd.append("--reload")

    print(f"🛡️  Trepan Gatekeeper starting on http://{args.host}:{args.port}")
    print(f"   Docs: http://{args.host}:{args.port}/docs")
    print(f"   Press Ctrl+C to stop.\n")
    
    # TRANSPARENCY FIX: Network accessibility warning
    if args.host == "127.0.0.1":
        print("⚠️  WARNING: Server bound to 127.0.0.1 (localhost only)")
        print("   If running in WSL and VS Code extension shows 'offline':")
        print("   Restart with: python start_server.py --host 0.0.0.0")
        print("")
    elif args.host == "0.0.0.0":
        print("✅ Server bound to 0.0.0.0 (accessible from Windows/WSL)")
        print("")
    
    print("=" * 80)

    try:
        # TRANSPARENCY FIX: Wrap uvicorn execution with detailed error handling
        print(f"🚀 Executing: {' '.join(cmd)}")
        print(f"   Working directory: {project_root}")
        print(f"   Python executable: {sys.executable}")
        print(f"   Environment: {os.environ.get('CONDA_DEFAULT_ENV', 'system')}")
        print("")
        
        # Start the process with detailed monitoring
        process = subprocess.Popen(
            cmd, 
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Monitor the process output in real-time using a separate thread
        import threading
        
        def stream_logs(proc):
            for line in proc.stdout:
                print(f"   {line.rstrip()}")

        log_thread = threading.Thread(target=stream_logs, args=(process,), daemon=True)
        log_thread.start()
        
        # Monitor the process output for startup detection (peek via poll or wait)
        startup_timeout = 30  # seconds
        startup_time = 0
        server_started = False
        
        print("📡 Server startup monitoring (streaming logs above):")
        # Since the thread is printing, we just wait for the process to be ready
        # or for a timeout. We can check the health endpoint to confirm startup.
        
        while startup_time < startup_timeout:
            if process.poll() is not None:
                print(f"❌ Server process terminated with exit code {process.returncode}")
                break
            
            # Simple health check to confirm server is up
            try:
                import urllib.request
                with urllib.request.urlopen(f"http://{args.host}:{args.port}/health", timeout=1) as resp:
                    if resp.status == 200:
                        server_started = True
                        print("\n✅ Server startup detected via health check!")
                        break
            except:
                pass
                
            startup_time += 1.0
            time.sleep(1.0)
        
        # If server started successfully, wait for it to finish
        if server_started or process.poll() is None:
            print("🔄 Server running - press Ctrl+C to stop")
            try:
                process.wait()  # Wait for process to complete
            except KeyboardInterrupt:
                print("\n🛑 Keyboard interrupt received - stopping server...")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print("⚠️  Server didn't stop gracefully, forcing termination...")
                    process.kill()
                    process.wait()
        
        # Check final exit code
        exit_code = process.returncode
        if exit_code == 0:
            print("✅ Server stopped cleanly")
        elif exit_code == -2 or exit_code == 130:  # SIGINT
            print("✅ Server stopped by user (Ctrl+C)")
        else:
            print(f"❌ Server exited with error code {exit_code}")
            
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Server failed to start (CalledProcessError)")
        print(f"   Exit code: {e.returncode}")
        print(f"   Command: {' '.join(cmd)}")
        print(f"   Working directory: {project_root}")
        if e.stdout:
            print(f"   Stdout: {e.stdout}")
        if e.stderr:
            print(f"   Stderr: {e.stderr}")
        
        # Additional diagnostics for common issues
        if e.returncode == 1:
            print("\n🔍 Common causes for exit code 1:")
            print("   - Python import errors (missing dependencies)")
            print("   - Syntax errors in server code")
            print("   - Configuration file issues")
            print("   - Permission problems")
        elif e.returncode == 127:
            print("\n🔍 Exit code 127 indicates:")
            print("   - Command not found (uvicorn not installed?)")
            print("   - PATH issues")
            print("   Run: pip install uvicorn")
            
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"\n❌ Server startup failed (FileNotFoundError)")
        print(f"   Error: {e}")
        print(f"   Python executable: {sys.executable}")
        print(f"   Working directory: {project_root}")
        print("\n🔍 This usually means:")
        print("   - Python is not in PATH")
        print("   - Virtual environment is not activated")
        print("   - uvicorn is not installed")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user.")
    except Exception as e:
        print(f"\n❌ Unexpected server error: {str(e)}")
        print(f"   Error type: {type(e).__name__}")
        print(f"   Python executable: {sys.executable}")
        print(f"   Working directory: {project_root}")
        import traceback
        print("\n📋 Full traceback:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
#python prepare_trepan_model.py && python start_server.py
#python prepare_trepan_model.py && python start_server.py --host 0.0.0.0
#python prepare_trepan_model.py && python start_server.py --host 0.0.0.0 --port 8001