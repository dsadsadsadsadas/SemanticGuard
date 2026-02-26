#!/usr/bin/env python3
"""
Convert Trepan model from .safetensors to .bin format
and verify it loads correctly.
"""

import json
import torch
from pathlib import Path

def convert_safetensors_to_bin(model_path: str):
    """Convert .safetensors adapter to .bin format"""
    
    model_path = Path(model_path)
    safetensors_file = model_path / "adapter_model.safetensors"
    bin_file = model_path / "adapter_model.bin"
    
    print(f"📦 Converting Trepan model format...")
    print(f"   Input:  {safetensors_file}")
    print(f"   Output: {bin_file}\n")
    
    # Check if .safetensors exists
    if not safetensors_file.exists():
        print(f"❌ File not found: {safetensors_file}")
        return False
    
    try:
        # Import safetensors
        from safetensors.torch import load_file
        print(f"[*] Loading {safetensors_file.name}...")
        state_dict = load_file(str(safetensors_file))
        
        # Save as .bin
        print(f"[*] Saving as {bin_file.name}...")
        torch.save(state_dict, str(bin_file))
        
        print(f"✅ Conversion complete!\n")
        return True
    
    except ImportError:
        print(f"❌ safetensors not installed")
        print(f"   Install: pip install safetensors")
        return False
    except Exception as e:
        print(f"❌ Conversion failed: {str(e)}")
        return False

def verify_model(model_path: str):
    """Verify model files and config"""
    
    model_path = Path(model_path)
    
    print(f"🔍 Verifying model at: {model_path}\n")
    
    # Check required files
    required_files = [
        "adapter_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
    ]
    
    # Check for either .bin or .safetensors
    has_weights = (model_path / "adapter_model.bin").exists() or \
                  (model_path / "adapter_model.safetensors").exists()
    
    required_files.append("adapter_model.bin OR adapter_model.safetensors")
    
    print("📋 Checking files:")
    all_good = True
    
    for file in required_files:
        if " OR " in file:
            bin_exists = (model_path / "adapter_model.bin").exists()
            safe_exists = (model_path / "adapter_model.safetensors").exists()
            if bin_exists:
                print(f"  ✅ adapter_model.bin")
            elif safe_exists:
                print(f"  ✅ adapter_model.safetensors")
            else:
                print(f"  ❌ Neither adapter_model.bin nor .safetensors found")
                all_good = False
        else:
            if (model_path / file).exists():
                print(f"  ✅ {file}")
            else:
                print(f"  ❌ {file} (missing)")
                all_good = False
    
    # Check adapter config
    config_file = model_path / "adapter_config.json"
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
            
            print(f"\n⚙️  Adapter Config:")
            print(f"   Type: {config.get('peft_type', 'unknown')}")
            print(f"   r (rank): {config.get('r', 'unknown')}")
            print(f"   lora_alpha: {config.get('lora_alpha', 'unknown')}")
            
        except Exception as e:
            print(f"  ❌ Failed to read config: {str(e)}")
            all_good = False
    
    if all_good:
        print(f"\n✅ Model structure is valid!\n")
    else:
        print(f"\n⚠️  Some files are missing\n")
    
    return all_good

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Prepare Trepan model")
    parser.add_argument("--model-path", 
                       default="/mnt/c/Users/ethan/Documents/Projects/Trepan/Trepan_Model_V2",
                       help="Path to model directory")
    parser.add_argument("--convert-only", action="store_true",
                       help="Only convert, don't verify")
    args = parser.parse_args()
    
    print("=" * 80)
    print("TREPAN MODEL PREPARATION")
    print("=" * 80 + "\n")
    
    # Convert if needed
    safetensors_file = Path(args.model_path) / "adapter_model.safetensors"
    bin_file = Path(args.model_path) / "adapter_model.bin"
    
    if safetensors_file.exists() and not bin_file.exists():
        print("🔄 Detected .safetensors format, converting...\n")
        if not convert_safetensors_to_bin(args.model_path):
            return False
    elif bin_file.exists():
        print("✅ Model already in .bin format\n")
    
    # Verify
    if not args.convert_only:
        if not verify_model(args.model_path):
            return False
    
    print("=" * 80)
    print("✅ Model is ready to use!")
    print("=" * 80)
    
    return True

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)