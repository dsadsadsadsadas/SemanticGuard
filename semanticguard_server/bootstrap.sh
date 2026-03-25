#!/usr/bin/env bash
# 🛡️ SemanticGuard Gatekeeper — Linux/macOS Bootstrap Script

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/venv_semanticguard_server"
SERVER_PORT=8000
ADAPTER_DIR="$PROJECT_ROOT/SemanticGuard_Model_V2"

echo ""
echo "========================================================"
echo "  🛡️  SemanticGuard Gatekeeper — Backend Bootstrap"
echo "========================================================"
echo ""

# ── 1. Check Python ──────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found. Install Python 3.10+ first."
    exit 1
fi
echo "[OK] $(python3 --version)"

# ── 2. Check CUDA ─────────────────────────────────────────
python3 -c "
import importlib.util
if importlib.util.find_spec('torch'):
    import torch
    print(f'[OK] PyTorch {torch.__version__} | CUDA: {torch.cuda.is_available()}')
else:
    print('[WARN] PyTorch not installed yet')
" 2>/dev/null || true
echo ""

# ── 3. Create venv ────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] Creating virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

# ── 4. Activate venv ──────────────────────────────────────
source "$VENV_DIR/bin/activate"

# ── 5. Install dependencies ───────────────────────────────
echo "[INFO] Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"

# ── 6. Install Unsloth ────────────────────────────────────
echo "[INFO] Installing Unsloth..."
pip install --quiet "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git" 2>/dev/null \
  || pip install --quiet unsloth 2>/dev/null \
  || echo "[WARN] Unsloth install failed — will use transformers fallback"

# ── 7. Verify model adapter ───────────────────────────────
if [ ! -f "$ADAPTER_DIR/adapter_model.safetensors" ]; then
    echo "[ERROR] SemanticGuard_Model_V2 adapter not found at: $ADAPTER_DIR"
    echo "        Ensure the SemanticGuard_Model_V2 folder is in the project root."
    exit 1
fi
echo "[OK] SemanticGuard_Model_V2 adapter found."

# ── 8. Start server ───────────────────────────────────────
echo ""
echo "[INFO] Starting SemanticGuard Gatekeeper on port $SERVER_PORT..."
echo "[INFO] Press Ctrl+C to stop."
echo ""
cd "$PROJECT_ROOT"
python3 -m uvicorn semanticguard_server.server:app \
    --host 127.0.0.1 \
    --port "$SERVER_PORT" \
    --log-level info
