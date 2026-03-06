#!/usr/bin/env python3
"""
Test file for CUDA pivot detection
This file will be used to test the automatic pivot detection system
"""

# Step 1: Add CUDA import (commit this)
import torch
import numpy as np

def process_data_with_cuda():
    """Process data using CUDA acceleration"""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = torch.tensor([1, 2, 3, 4, 5]).to(device)
    result = data * 2
    return result.cpu().numpy()

if __name__ == "__main__":
    print("Testing CUDA...")
    result = process_data_with_cuda()
    print(f"Result: {result}")
