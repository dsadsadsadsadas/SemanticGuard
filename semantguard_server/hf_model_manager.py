#!/usr/bin/env python3
"""
🛡️ SemantGuard Gatekeeper — HuggingFace Model Uploader/Downloader
Handles pushing SemantGuard_Model_V2 to HF Hub and downloading on new machines.

Usage:
    # Upload (one-time, for the model author)
    python hf_model_manager.py upload --repo YOUR_USERNAME/SemantGuard_Model_V2

    # Download (for new users)
    python hf_model_manager.py download --repo YOUR_USERNAME/SemantGuard_Model_V2

    # Check if model exists locally or on HF
    python hf_model_manager.py status --repo YOUR_USERNAME/SemantGuard_Model_V2
"""

import argparse
import sys
from pathlib import Path

ADAPTER_DIR = Path(__file__).parent.parent / "SemantGuard_Model_V2"


def _ensure_hub():
    try:
        from huggingface_hub import HfApi, snapshot_download, login  # noqa: F401
        return True
    except ImportError:
        print("❌ huggingface_hub not installed.")
        print("   Run: pip install huggingface_hub")
        sys.exit(1)


def cmd_upload(repo: str, token: str | None):
    _ensure_hub()
    from huggingface_hub import HfApi, login

    print(f"🚀 Uploading SemantGuard_Model_V2 → {repo}")
    print(f"   Source: {ADAPTER_DIR.resolve()}")

    if not ADAPTER_DIR.exists():
        print(f"❌ Adapter directory not found: {ADAPTER_DIR}")
        sys.exit(1)

    if token:
        login(token=token)
    else:
        login()  # Interactive login

    api = HfApi()

    # Create repo if it doesn't exist
    try:
        api.create_repo(repo_id=repo, repo_type="model", exist_ok=True, private=False)
        print(f"✅ Repository ensured: https://huggingface.co/{repo}")
    except Exception as e:
        print(f"⚠️  Could not create repo (may already exist): {e}")

    # Upload all adapter files
    upload_files = [
        "adapter_config.json",
        "adapter_model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "README.md",
    ]

    for filename in upload_files:
        src = ADAPTER_DIR / filename
        if not src.exists():
            print(f"   ⏭️  Skipping {filename} (not found)")
            continue
        print(f"   ⬆️  Uploading {filename} ({src.stat().st_size / 1_048_576:.1f} MB)…")
        api.upload_file(
            path_or_fileobj=str(src),
            path_in_repo=filename,
            repo_id=repo,
            repo_type="model",
        )
        print(f"   ✅ {filename} uploaded")

    print(f"\n✨ Upload complete!")
    print(f"   View at: https://huggingface.co/{repo}")
    print(f"   Update bootstrap.bat/sh with: HF_REPO={repo}")


def cmd_download(repo: str, token: str | None):
    _ensure_hub()
    from huggingface_hub import snapshot_download, login

    print(f"⬇️  Downloading {repo} → {ADAPTER_DIR.resolve()}")

    if ADAPTER_DIR.exists() and (ADAPTER_DIR / "adapter_model.safetensors").exists():
        print("✅ Model already exists locally — skipping download.")
        print("   (Delete SemantGuard_Model_V2/ and re-run to force re-download)")
        return

    if token:
        login(token=token)

    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)

    print("   This may take a few minutes (model is ~320 MB)…")
    snapshot_download(
        repo_id=repo,
        local_dir=str(ADAPTER_DIR),
        repo_type="model",
        ignore_patterns=["checkpoint-*"],  # skip training checkpoints
    )
    print(f"\n✅ SemantGuard_Model_V2 downloaded to {ADAPTER_DIR.resolve()}")


def cmd_status(repo: str):
    _ensure_hub()
    from huggingface_hub import HfApi

    local_ok = (ADAPTER_DIR / "adapter_model.safetensors").exists()
    print(f"📦 Local adapter  : {'✅ Found' if local_ok else '❌ Missing'} ({ADAPTER_DIR})")

    api = HfApi()
    try:
        info = api.model_info(repo)
        print(f"☁️  HuggingFace    : ✅ Exists — https://huggingface.co/{repo}")
        print(f"   Last modified  : {info.last_modified}")
    except Exception:
        print(f"☁️  HuggingFace    : ❌ Not found or private — {repo}")


def main():
    parser = argparse.ArgumentParser(description="🛡️ SemantGuard Model Manager (HuggingFace)")
    parser.add_argument("command", choices=["upload", "download", "status"])
    parser.add_argument("--repo",  required=True, help="HF repo ID, e.g. your-username/SemantGuard_Model_V2")
    parser.add_argument("--token", default=None,  help="HF access token (optional, uses cached login otherwise)")
    args = parser.parse_args()

    if args.command == "upload":
        cmd_upload(args.repo, args.token)
    elif args.command == "download":
        cmd_download(args.repo, args.token)
    elif args.command == "status":
        cmd_status(args.repo)


if __name__ == "__main__":
    main()
