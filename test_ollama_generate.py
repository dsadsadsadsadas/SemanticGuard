#!/usr/bin/env python3
"""Test script to verify Ollama generation works"""

import sys
sys.path.insert(0, '.')

from trepan_server.server import generate_with_ollama

try:
    print("Testing Ollama generation...")
    result = generate_with_ollama("Say hello in one sentence.")
    print(f"Success! Result: {result}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
