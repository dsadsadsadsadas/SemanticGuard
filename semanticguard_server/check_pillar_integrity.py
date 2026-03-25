#!/usr/bin/env python3
import os
import sys
import hashlib
import argparse
import shutil
from datetime import datetime

try:
    from server import PILLARS, get_root_dir, write_vault_lock
except ImportError:
    # Fallbacks in case running directly fails
    PILLARS = [
        "golden_state.md",
        "done_tasks.md",
        "pending_tasks.md",
        "history_phases.md",
        "system_rules.md",
        "problems_and_resolutions.md",
    ]
    def get_root_dir() -> str:
        # Dynamically resolve root relative to this script
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def write_vault_lock(root_dir: str):
        pass # Only used if importing server fails, which we hope it doesn't


def get_md5(file_path: str) -> str:
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Check SemanticGuard pillar integrity.")
    parser.add_argument("--sync", action="store_true", help="Auto-heal missing or out of sync files")
    args = parser.parse_args()

    root_dir = get_root_dir()
    semanticguard_dir = os.path.join(root_dir, ".semanticguard")
    vault_dir = os.path.join(semanticguard_dir, "semanticguard_vault")

    print("="*80)
    print("🛡️ SEMANTICGUARD PILLAR INTEGRITY CHECK")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    print(f"{'PILLAR':<30} | {'PRESENCE (LIVE/VAULT)':<25} | {'SYNC STATUS':<15}")
    print("-" * 80)

    out_of_sync_count = 0
    missing_count = 0

    for pillar in PILLARS:
        live_path = os.path.join(semanticguard_dir, pillar)
        vault_path = os.path.join(vault_dir, pillar)

        live_exists = os.path.exists(live_path)
        vault_exists = os.path.exists(vault_path)

        presence_str = f"{'EXISTS' if live_exists else 'MISSING'} / {'EXISTS' if vault_exists else 'MISSING'}"
        
        status_str = ""

        if not live_exists and not vault_exists:
            status_str = "N/A"
        elif not live_exists:
            status_str = "MISSING IN LIVE"
            missing_count += 1
        elif not vault_exists:
            status_str = "MISSING IN VAULT"
            missing_count += 1
            out_of_sync_count += 1
        else:
            live_md5 = get_md5(live_path)
            vault_md5 = get_md5(vault_path)
            if live_md5 == vault_md5:
                status_str = "IN SYNC ✅"
            else:
                status_str = "OUT OF SYNC 🛑"
                out_of_sync_count += 1

        print(f"{pillar:<30} | {presence_str:<25} | {status_str:<15}")

        if args.sync and status_str in ["MISSING IN VAULT", "OUT OF SYNC 🛑"]:
            if live_exists:
                os.makedirs(vault_dir, exist_ok=True)
                # Atomic temp-then-rename for healing
                temp_vault_path = vault_path + ".tmp"
                shutil.copy2(live_path, temp_vault_path)
                os.replace(temp_vault_path, vault_path)
                print(f"   ↳ [AUTO-HEAL] Synced {pillar} to vault.")

    print("-" * 80)
    if out_of_sync_count == 0 and missing_count == 0:
        print("✅ All pillars are perfectly in sync.")
    else:
        print(f"🛑 Found {out_of_sync_count} files out of sync or missing.")
        if args.sync:
            print("🔄 [AUTO-HEAL] Resigning vault lock...")
            try:
                from server import write_vault_lock
                write_vault_lock(root_dir)
                print("✅ Vault cryptographically re-signed!")
            except Exception as e:
                print(f"❌ Could not automatically re-sign vault: {e}")
                print("   Please hit the /resign_vault endpoint manually.")
        else:
            print("💡 TIP: Run with --sync to auto-heal the vault.")
    print("="*80)

if __name__ == "__main__":
    main()
