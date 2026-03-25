@echo off
REM SemanticGuard Server Startup Script (Windows)
REM This script starts the SemanticGuard server from the correct directory

echo.
echo ========================================
echo   TREPAN GATEKEEPER SERVER
echo ========================================
echo.

REM Check if Ollama is running
echo [1/3] Checking Ollama connection...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Ollama is not running!
    echo.
    echo Please start Ollama first:
    echo   1. Open a new terminal
    echo   2. Run: ollama serve
    echo   3. Then run this script again
    echo.
    pause
    exit /b 1
)
echo [OK] Ollama is running

REM Check if llama3.1:8b model is installed
echo [2/3] Checking if llama3.1:8b model is installed...
curl -s http://localhost:11434/api/tags | findstr "llama3.1" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [WARNING] llama3.1:8b model not found!
    echo.
    echo Installing llama3.1:8b model...
    ollama pull llama3.1:8b
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install model
        pause
        exit /b 1
    )
)
echo [OK] llama3.1:8b model is installed

REM Start the server
echo [3/3] Starting SemanticGuard server...
echo.
echo Server will be available at: http://127.0.0.1:8000
echo Press CTRL+C to stop the server
echo.

REM Run from parent directory so imports work correctly
python -m uvicorn semanticguard_server.server:app --reload --host 127.0.0.1 --port 8000
