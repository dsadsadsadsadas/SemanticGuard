#!/usr/bin/env python3
"""
GPU Verification Script for Trepan
Run this after installing CUDA-enabled PyTorch.
"""

import torch

print("=" * 50)
print("TREPAN GPU VERIFICATION")
print("=" * 50)

print(f"\nTORCH VERSION: {torch.__version__}")
print(f"CUDA AVAILABLE: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"DEVICE NAME: {torch.cuda.get_device_name(0)}")
    print(f"CUDA VERSION: {torch.version.cuda}")
    
    # Get VRAM info
    total_mem = torch.cuda.get_device_properties(0).total_memory / 1024 / 1024 / 1024
    print(f"VRAM: {total_mem:.1f} GB")
    
    # Quick tensor test
    x = torch.randn(1000, 1000, device='cuda')
    y = torch.randn(1000, 1000, device='cuda')
    z = x @ y  # Matrix multiply on GPU
    print(f"\nGPU TENSOR TEST: PASSED (1000x1000 matmul)")
    print("STATUS: GPU ONLINE - Ready for Drift Engine")
else:
    print("\nSTATUS: STILL ON CPU")
    print("Possible issues:")
    print("  1. Wrong PyTorch version (need CUDA build)")
    print("  2. NVIDIA drivers not installed")
    print("  3. CUDA toolkit not installed")
    print("\nFix: pip install torch --index-url https://download.pytorch.org/whl/cu121")

print("=" * 50)
