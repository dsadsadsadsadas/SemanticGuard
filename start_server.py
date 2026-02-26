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
import subprocess
import sys
from pathlib import Path

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

def main():
    parser = argparse.ArgumentParser(description="Start the Trepan Gatekeeper server")
    parser.add_argument("--port",            type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--host",            default="127.0.0.1",   help="Host (default: 127.0.0.1)")
    parser.add_argument("--reload",          action="store_true",   help="Dev mode (auto-reload)")
    parser.add_argument("--skip-sklearn",    action="store_true",   help="Skip sklearn check")
    parser.add_argument("--check-only",      action="store_true",   help="Only check deps, don't start")
    args = parser.parse_args()

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
    print("=" * 80)

    try:
        subprocess.run(cmd, cwd=str(project_root))
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped.")
    except Exception as e:
        print(f"\n❌ Server error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
#python prepare_trepan_model.py && python start_server.py