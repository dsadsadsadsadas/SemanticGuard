#!/usr/bin/env python3
"""
SemanticGuard Setup Verification Script
Checks that all required dependencies are installed correctly.
"""

import sys

def check_python_version():
    """Verify Python version is 3.9+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print(f"❌ Python {version.major}.{version.minor} detected")
        print("   SemanticGuard requires Python 3.9 or higher")
        print("   Download: https://www.python.org/downloads/")
        return False
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    return True

def check_dependencies():
    """Verify all required packages are installed"""
    required = [
        ('fastapi', 'FastAPI web framework'),
        ('uvicorn', 'ASGI server'),
        ('pydantic', 'Data validation'),
        ('requests', 'HTTP client'),
        ('tree_sitter', 'Code parser'),
    ]
    
    optional = [
        ('ollama', 'Local LLM support (optional)'),
        ('httpx', 'Async HTTP client (optional)'),
    ]
    
    all_ok = True
    
    print("\nCore Dependencies:")
    for package, description in required:
        try:
            __import__(package)
            print(f"  ✓ {package:20s} - {description}")
        except ImportError:
            print(f"  ❌ {package:20s} - {description} (MISSING)")
            all_ok = False
    
    print("\nOptional Dependencies:")
    for package, description in optional:
        try:
            __import__(package)
            print(f"  ✓ {package:20s} - {description}")
        except ImportError:
            print(f"  ⚠ {package:20s} - {description} (not installed)")
    
    return all_ok

def check_server():
    """Check if server can be imported"""
    try:
        sys.path.insert(0, 'semanticguard_server')
        import server
        print("\n✓ SemanticGuard server module can be imported")
        return True
    except Exception as e:
        print(f"\n❌ Server import failed: {e}")
        return False

def main():
    print("═" * 60)
    print("SemanticGuard Setup Verification")
    print("═" * 60)
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Server Module", check_server),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append(result)
        except Exception as e:
            print(f"\n❌ {name} check failed: {e}")
            results.append(False)
    
    print("\n" + "═" * 60)
    if all(results):
        print("✅ All checks passed! SemanticGuard is ready to use.")
        print("\nNext steps:")
        print("  1. Start the server: python start_server.py")
        print("  2. Open VS Code and install the SemanticGuard extension")
        print("  3. Configure your API key (optional for Power Mode)")
        return 0
    else:
        print("❌ Some checks failed. Please install missing dependencies:")
        print("\n  pip install -r requirements.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main())
