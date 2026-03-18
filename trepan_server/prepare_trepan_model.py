#!/usr/bin/env python3
"""
Convert Trepan model from .safetensors to .bin format
and verify it loads correctly with comprehensive diagnostics.
"""

import json
import os
import torch
from pathlib import Path

def convert_safetensors_to_bin(model_path: str):
    """Convert .safetensors adapter to .bin format with detailed diagnostics"""
    
    model_path = Path(model_path)
    safetensors_file = model_path / "adapter_model.safetensors"
    bin_file = model_path / "adapter_model.bin"
    
    print(f"📦 Converting Trepan model format...")
    print(f"   Input:  {safetensors_file}")
    print(f"   Output: {bin_file}")
    print(f"   Input exists: {safetensors_file.exists()}")
    print(f"   Output exists: {bin_file.exists()}")
    print("")
    
    # Check if .safetensors exists with detailed diagnostics
    if not safetensors_file.exists():
        print(f"❌ CONVERSION FAILED: Input file not found")
        print(f"   Expected: {safetensors_file.absolute()}")
        print(f"   Parent directory exists: {safetensors_file.parent.exists()}")
        
        if safetensors_file.parent.exists():
            try:
                files_in_dir = list(safetensors_file.parent.iterdir())
                print(f"   Files in directory ({len(files_in_dir)}):")
                for f in sorted(files_in_dir):
                    print(f"     - {f.name}")
            except Exception as e:
                print(f"   Could not list directory: {e}")
        
        return False
    
    # Check file size and readability
    try:
        file_size = safetensors_file.stat().st_size
        print(f"📊 Input file analysis:")
        print(f"   Size: {file_size / (1024*1024):.1f} MB ({file_size:,} bytes)")
        print(f"   Readable: {os.access(safetensors_file, os.R_OK)}")
        print(f"   Writable directory: {os.access(model_path, os.W_OK)}")
        print("")
        
        if file_size == 0:
            print(f"❌ CONVERSION FAILED: Input file is empty")
            return False
            
        if file_size < 1024:  # Less than 1KB is suspicious for a model
            print(f"⚠️  WARNING: Input file is very small ({file_size} bytes)")
            print(f"   This may not be a valid model file")
            
    except Exception as e:
        print(f"❌ CONVERSION FAILED: Cannot analyze input file: {e}")
        return False
    
    try:
        # Import safetensors with error handling
        try:
            from safetensors.torch import load_file
            print(f"✅ SafeTensors library imported successfully")
        except ImportError as ie:
            print(f"❌ CONVERSION FAILED: SafeTensors not installed")
            print(f"   Error: {ie}")
            print(f"   Install with: pip install safetensors")
            return False
        
        # Load the safetensors file
        print(f"🔄 Loading {safetensors_file.name}...")
        try:
            state_dict = load_file(str(safetensors_file))
            print(f"✅ SafeTensors file loaded successfully")
            print(f"   Parameters found: {len(state_dict)}")
            
            if len(state_dict) == 0:
                print(f"❌ CONVERSION FAILED: No parameters in SafeTensors file")
                return False
                
            # Show parameter info
            total_params = sum(tensor.numel() for tensor in state_dict.values())
            print(f"   Total parameter count: {total_params:,}")
            
            if len(state_dict) > 0:
                first_key = list(state_dict.keys())[0]
                first_tensor = state_dict[first_key]
                print(f"   Sample parameter: {first_key} {list(first_tensor.shape)} ({first_tensor.dtype})")
                
        except Exception as load_err:
            print(f"❌ CONVERSION FAILED: Could not load SafeTensors file")
            print(f"   Error: {load_err}")
            print(f"   File may be corrupted or in wrong format")
            return False
        
        # Save as .bin with error handling
        print(f"💾 Saving as {bin_file.name}...")
        try:
            import torch
            torch.save(state_dict, str(bin_file))
            print(f"✅ PyTorch .bin file saved successfully")
            
            # Verify the saved file
            saved_size = bin_file.stat().st_size
            print(f"   Output size: {saved_size / (1024*1024):.1f} MB ({saved_size:,} bytes)")
            
            # Quick verification load
            try:
                verification_dict = torch.load(str(bin_file), map_location='cpu')
                if len(verification_dict) == len(state_dict):
                    print(f"✅ Verification passed: {len(verification_dict)} parameters loaded from .bin")
                else:
                    print(f"⚠️  Verification warning: Parameter count mismatch")
                    print(f"   Original: {len(state_dict)}, Saved: {len(verification_dict)}")
            except Exception as verify_err:
                print(f"⚠️  Verification failed: {verify_err}")
                print(f"   File was saved but may have issues")
                
        except Exception as save_err:
            print(f"❌ CONVERSION FAILED: Could not save .bin file")
            print(f"   Error: {save_err}")
            print(f"   Check disk space and write permissions")
            return False
        
        print(f"\n✅ CONVERSION COMPLETED SUCCESSFULLY")
        print(f"   Input:  {safetensors_file.name} ({file_size / (1024*1024):.1f} MB)")
        print(f"   Output: {bin_file.name} ({bin_file.stat().st_size / (1024*1024):.1f} MB)")
        print("")
        return True
    
    except Exception as e:
        print(f"❌ CONVERSION FAILED: Unexpected error during conversion")
        print(f"   Error: {str(e)}")
        import traceback
        print(f"   Full traceback:")
        traceback.print_exc()
        return False

def verify_model(model_path: str):
    """Verify model files and config with detailed diagnostics"""
    
    model_path = Path(model_path)
    
    print(f"🔍 Verifying model at: {model_path}")
    print(f"   Absolute path: {model_path.absolute()}")
    print(f"   Directory exists: {model_path.exists()}")
    print(f"   Is directory: {model_path.is_dir()}")
    print("")
    
    if not model_path.exists():
        print(f"❌ CRITICAL: Model directory does not exist!")
        print(f"   Expected: {model_path.absolute()}")
        print(f"   Parent exists: {model_path.parent.exists()}")
        return False
    
    if not model_path.is_dir():
        print(f"❌ CRITICAL: Path exists but is not a directory!")
        print(f"   Path type: {type(model_path)}")
        return False
    
    # List all files in directory for transparency
    try:
        all_files = list(model_path.iterdir())
        print(f"📁 Directory contents ({len(all_files)} items):")
        for item in sorted(all_files):
            size_info = ""
            if item.is_file():
                try:
                    size = item.stat().st_size
                    if size > 1024*1024:  # > 1MB
                        size_info = f" ({size / (1024*1024):.1f} MB)"
                    elif size > 1024:  # > 1KB
                        size_info = f" ({size / 1024:.1f} KB)"
                    else:
                        size_info = f" ({size} bytes)"
                except:
                    size_info = " (size unknown)"
            print(f"   {'📄' if item.is_file() else '📁'} {item.name}{size_info}")
        print("")
    except Exception as e:
        print(f"❌ Could not list directory contents: {e}")
        return False
    
    # Check required files with detailed diagnostics
    required_files = [
        "adapter_config.json",
        "tokenizer.json", 
        "tokenizer_config.json",
    ]
    
    print("📋 Checking required files:")
    all_good = True
    
    for file in required_files:
        file_path = model_path / file
        if file_path.exists():
            try:
                size = file_path.stat().st_size
                print(f"  ✅ {file} ({size} bytes)")
                
                # Validate JSON files can be parsed
                if file.endswith('.json'):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            json.load(f)
                        print(f"     └─ JSON structure valid")
                    except json.JSONDecodeError as je:
                        print(f"     └─ ❌ JSON parse error: {je}")
                        all_good = False
                    except Exception as je:
                        print(f"     └─ ❌ JSON read error: {je}")
                        all_good = False
                        
            except Exception as e:
                print(f"  ❌ {file} (exists but cannot read: {e})")
                all_good = False
        else:
            print(f"  ❌ {file} (missing)")
            print(f"     └─ Expected at: {file_path.absolute()}")
            all_good = False
    
    # Check for model weights with detailed diagnostics
    print(f"\n🏋️  Checking model weights:")
    bin_file = model_path / "adapter_model.bin"
    safetensors_file = model_path / "adapter_model.safetensors"
    
    bin_exists = bin_file.exists()
    safe_exists = safetensors_file.exists()
    
    if bin_exists:
        try:
            size = bin_file.stat().st_size
            print(f"  ✅ adapter_model.bin ({size / (1024*1024):.1f} MB)")
            
            # Try to load the .bin file to verify it's valid
            try:
                import torch
                state_dict = torch.load(str(bin_file), map_location='cpu')
                num_params = len(state_dict)
                print(f"     └─ PyTorch tensor dict loaded successfully ({num_params} parameters)")
                
                # Show some parameter info
                if num_params > 0:
                    first_key = list(state_dict.keys())[0]
                    first_tensor = state_dict[first_key]
                    print(f"     └─ Sample parameter: {first_key} {list(first_tensor.shape)}")
                    
            except Exception as load_err:
                print(f"     └─ ❌ PyTorch load failed: {load_err}")
                all_good = False
                
        except Exception as e:
            print(f"  ❌ adapter_model.bin (exists but cannot read: {e})")
            all_good = False
            
    elif safe_exists:
        try:
            size = safetensors_file.stat().st_size
            print(f"  ✅ adapter_model.safetensors ({size / (1024*1024):.1f} MB)")
            
            # Try to load the .safetensors file to verify it's valid
            try:
                from safetensors.torch import load_file
                state_dict = load_file(str(safetensors_file))
                num_params = len(state_dict)
                print(f"     └─ SafeTensors loaded successfully ({num_params} parameters)")
                
                # Show some parameter info
                if num_params > 0:
                    first_key = list(state_dict.keys())[0]
                    first_tensor = state_dict[first_key]
                    print(f"     └─ Sample parameter: {first_key} {list(first_tensor.shape)}")
                    
            except ImportError:
                print(f"     └─ ⚠️  SafeTensors not installed - cannot verify file integrity")
                print(f"     └─ Install with: pip install safetensors")
            except Exception as load_err:
                print(f"     └─ ❌ SafeTensors load failed: {load_err}")
                all_good = False
                
        except Exception as e:
            print(f"  ❌ adapter_model.safetensors (exists but cannot read: {e})")
            all_good = False
    else:
        print(f"  ❌ No model weights found!")
        print(f"     └─ Expected: {bin_file.absolute()}")
        print(f"     └─ Or: {safetensors_file.absolute()}")
        all_good = False
    
    # Check adapter config with detailed analysis
    config_file = model_path / "adapter_config.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            print(f"\n⚙️  Adapter Configuration Analysis:")
            print(f"   Type: {config.get('peft_type', 'unknown')}")
            print(f"   Rank (r): {config.get('r', 'unknown')}")
            print(f"   LoRA Alpha: {config.get('lora_alpha', 'unknown')}")
            print(f"   Target Modules: {config.get('target_modules', 'unknown')}")
            print(f"   Task Type: {config.get('task_type', 'unknown')}")
            
            # Validate critical config values
            if config.get('peft_type') != 'LORA':
                print(f"     └─ ⚠️  Expected PEFT type 'LORA', got '{config.get('peft_type')}'")
                
            if not isinstance(config.get('r'), int) or config.get('r', 0) <= 0:
                print(f"     └─ ❌ Invalid rank (r): {config.get('r')} (should be positive integer)")
                all_good = False
                
            if not isinstance(config.get('lora_alpha'), (int, float)) or config.get('lora_alpha', 0) <= 0:
                print(f"     └─ ❌ Invalid lora_alpha: {config.get('lora_alpha')} (should be positive number)")
                all_good = False
                
        except json.JSONDecodeError as e:
            print(f"  ❌ adapter_config.json is not valid JSON: {e}")
            all_good = False
        except Exception as e:
            print(f"  ❌ Failed to analyze adapter config: {e}")
            all_good = False
    
    # Final verdict with specific failure reasons
    print(f"\n{'='*60}")
    if all_good:
        print(f"✅ MODEL VERIFICATION PASSED")
        print(f"   All required files present and valid")
        print(f"   Model weights can be loaded")
        print(f"   Configuration is valid")
    else:
        print(f"❌ MODEL VERIFICATION FAILED")
        print(f"   One or more critical issues found above")
        print(f"   Server may fail to start or produce errors")
        print(f"   Fix the issues and run verification again")
    print(f"{'='*60}\n")
    
    return all_good

def main():
    import argparse
    import sys
    
    # Dynamically resolve root directory irrespective of Windows/WSL
    base_dir = Path(__file__).parent.parent
    default_model_path = base_dir / "Trepan_Model_V2"
    
    parser = argparse.ArgumentParser(description="Prepare Trepan model with comprehensive diagnostics")
    parser.add_argument("--model-path", 
                       default=str(default_model_path),
                       help="Path to model directory")
    parser.add_argument("--convert-only", action="store_true",
                       help="Only convert, don't verify")
    parser.add_argument("--verify-only", action="store_true", 
                       help="Only verify, don't convert")
    args = parser.parse_args()
    
    print("=" * 80)
    print("🛡️  TREPAN MODEL PREPARATION & DIAGNOSTICS")
    print("=" * 80)
    print(f"Model Path: {args.model_path}")
    print(f"Convert Only: {args.convert_only}")
    print(f"Verify Only: {args.verify_only}")
    print(f"Python Version: {sys.version}")
    print(f"Working Directory: {os.getcwd()}")
    print("=" * 80 + "\n")
    
    # GPU Pre-flight Check
    print("🔍 PRE-FLIGHT GPU CHECK:")
    import shutil
    import subprocess
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            res = subprocess.run([smi], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                print("✅ GPU detected. Hardware acceleration available.")
            else:
                print("⚠️  GPU detected but nvidia-smi failed. Drivers may be unstable.")
        except:
            print("⚠️  Error checking GPU status.")
    else:
        print("❌ NO GPU DETECTED (nvidia-smi missing).")
        print("   If you have a GPU, please install NVIDIA drivers.")
        print("   Conversion will proceed using CPU, but inference will be SLOW.")
    print("-" * 40 + "\n")
    
    model_path = Path(args.model_path)
    
    # Check if model directory exists
    if not model_path.exists():
        print(f"❌ CRITICAL ERROR: Model directory does not exist!")
        print(f"   Expected: {model_path.absolute()}")
        print(f"   Current working directory: {os.getcwd()}")
        print(f"   Parent directory exists: {model_path.parent.exists()}")
        
        # Try to find similar directories
        if model_path.parent.exists():
            try:
                similar_dirs = [d for d in model_path.parent.iterdir() 
                              if d.is_dir() and 'trepan' in d.name.lower()]
                if similar_dirs:
                    print(f"   Similar directories found:")
                    for d in similar_dirs:
                        print(f"     - {d}")
                    print(f"   Use --model-path to specify the correct directory")
            except Exception as e:
                print(f"   Could not search for similar directories: {e}")
        
        print("\n" + "=" * 80)
        print("❌ MODEL PREPARATION FAILED - DIRECTORY NOT FOUND")
        print("=" * 80)
        return False
    
    success = True
    
    # Conversion phase
    if not args.verify_only:
        safetensors_file = model_path / "adapter_model.safetensors"
        bin_file = model_path / "adapter_model.bin"
        
        if safetensors_file.exists() and not bin_file.exists():
            print("🔄 PHASE 1: FORMAT CONVERSION")
            print("Detected .safetensors format, converting to .bin...\n")
            if not convert_safetensors_to_bin(args.model_path):
                success = False
                print("❌ Conversion failed - stopping here")
                return False
        elif bin_file.exists():
            print("✅ PHASE 1: FORMAT CONVERSION")
            print("Model already in .bin format - no conversion needed\n")
        elif safetensors_file.exists() and bin_file.exists():
            print("ℹ️  PHASE 1: FORMAT CONVERSION")
            print("Both .safetensors and .bin formats exist - using .bin\n")
        else:
            print("⚠️  PHASE 1: FORMAT CONVERSION")
            print("No model weights found (.bin or .safetensors) - verification will fail\n")
    
    # Verification phase
    if not args.convert_only:
        print("🔍 PHASE 2: MODEL VERIFICATION")
        print("Performing comprehensive model validation...\n")
        if not verify_model(args.model_path):
            success = False
    
    # Final summary
    print("=" * 80)
    if success:
        print("✅ TREPAN MODEL PREPARATION COMPLETED SUCCESSFULLY")
        print("")
        print("🚀 Ready to start Trepan server!")
        print("   Next steps:")
        print("   1. Start Ollama: ollama serve")
        print("   2. Pull model: ollama pull llama3.1:8b") 
        print("   3. Start server: python start_server.py")
        print("   4. Check health: curl http://localhost:8000/health")
    else:
        print("❌ TREPAN MODEL PREPARATION FAILED")
        print("")
        print("🔧 Issues found that need to be resolved:")
        print("   - Check the error messages above")
        print("   - Ensure all required files are present")
        print("   - Verify file permissions and disk space")
        print("   - Run again after fixing issues")
    print("=" * 80)
    
    return success

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)