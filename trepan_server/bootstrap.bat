@echo off
:: 🛡️ Trepan Gatekeeper — Windows Bootstrap Script
:: Sets up the Python venv and starts the inference server.

setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set VENV_DIR=%PROJECT_ROOT%\venv_trepan_server
set SERVER_PORT=8000

echo.
echo ========================================================
echo   🛡️  Trepan Gatekeeper — Backend Bootstrap
echo ========================================================
echo.

:: ── 1. Check Python ──────────────────────────────────────
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Found %PY_VER%

:: ── 2. Check CUDA ─────────────────────────────────────────
python -c "import torch; print('[OK] CUDA available:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')" 2>nul
if %ERRORLEVEL% neq 0 (
    echo [WARN] PyTorch not found yet — will install below
)
echo.

:: ── 3. Create venv ────────────────────────────────────────
if not exist "%VENV_DIR%" (
    echo [INFO] Creating virtual environment at %VENV_DIR% ...
    python -m venv "%VENV_DIR%"
)

:: ── 4. Activate venv ──────────────────────────────────────
call "%VENV_DIR%\Scripts\activate.bat"

:: ── 5. Install dependencies ───────────────────────────────
echo [INFO] Installing core dependencies...
pip install --quiet --upgrade pip
pip install --quiet -r "%SCRIPT_DIR%requirements.txt"

:: ── 6. Install Unsloth (CUDA-specific) ───────────────────
echo [INFO] Installing Unsloth (this may take a few minutes)...
pip install --quiet "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git" 2>nul
if %ERRORLEVEL% neq 0 (
    echo [WARN] Unsloth git install failed — trying PyPI version...
    pip install --quiet unsloth 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [WARN] Unsloth not installed. Will use transformers fallback (slower).
    )
)

:: ── 7. Verify model exists ────────────────────────────────
set ADAPTER_DIR=%PROJECT_ROOT%\Trepan_Model_V2
if not exist "%ADAPTER_DIR%\adapter_model.safetensors" (
    echo [ERROR] Trepan_Model_V2 adapter not found at: %ADAPTER_DIR%
    echo         Please ensure the Trepan_Model_V2 folder is in the project root.
    echo         If you need to download it from HuggingFace, run:
    echo           pip install huggingface_hub
    echo           python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='YOUR_HF_REPO/Trepan_Model_V2', local_dir='%ADAPTER_DIR%')"
    pause
    exit /b 1
)
echo [OK] Trepan_Model_V2 adapter found.

:: ── 8. Start server ───────────────────────────────────────
echo.
echo [INFO] Starting Trepan Gatekeeper server on port %SERVER_PORT%...
echo [INFO] Press Ctrl+C to stop.
echo.
cd /d "%PROJECT_ROOT%"
python -m uvicorn trepan_server.server:app --host 127.0.0.1 --port %SERVER_PORT% --log-level info

endlocal
