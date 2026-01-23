
import sys
import logging

# Mock logger
logging.basicConfig(level=logging.INFO)

print("Starting verification...")

try:
    from hardware_sentinel import sentinel as hardware
    print(f"\n🖥️ COMPUTE ROUTER:")
    print(f"   - Device: {hardware.config.device.upper()}")
    print(f"   - Vector Ops: {hardware.route_task('VECTOR_SEARCH').upper()}")
    print(f"   - AST Ops: {hardware.route_task('AST_PARSING').upper()}")
    # This line caused the crash before:
    if hardware.config.vram_mb > 0:
        print(f"   - VRAM: {hardware.config.vram_mb:.0f}MB")
    print("✅ Fix Verification: SUCCESS")
except Exception as e:
    print(f"❌ Fix Verification: FAILED with {e}")
    sys.exit(1)
