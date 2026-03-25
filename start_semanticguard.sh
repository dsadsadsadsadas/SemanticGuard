#!/bin/bash
# SemanticGuard Server Startup Script (Linux/Mac)
# This script starts the SemanticGuard server from the correct directory

echo ""
echo "========================================"
echo "  SEMANTICGUARD GATEKEEPER SERVER"
echo "========================================"
echo ""

# Check if Ollama is running
echo "[1/3] Checking Ollama connection..."
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo ""
    echo "[ERROR] Ollama is not running!"
    echo ""
    echo "Please start Ollama first:"
    echo "  1. Open a new terminal"
    echo "  2. Run: ollama serve"
    echo "  3. Then run this script again"
    echo ""
    exit 1
fi
echo "[OK] Ollama is running"

# Check if llama3.1:8b model is installed
echo "[2/3] Checking if llama3.1:8b model is installed..."
if ! curl -s http://localhost:11434/api/tags | grep -q "llama3.1"; then
    echo ""
    echo "[WARNING] llama3.1:8b model not found!"
    echo ""
    echo "Installing llama3.1:8b model..."
    ollama pull llama3.1:8b
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install model"
        exit 1
    fi
fi
echo "[OK] llama3.1:8b model is installed"

# Start the server
echo "[3/3] Starting SemanticGuard server..."
echo ""
echo "Server will be available at: http://127.0.0.1:8000"
echo "Press CTRL+C to stop the server"
echo ""

# Run from parent directory so imports work correctly
python -m uvicorn semanticguard_server.server:app --reload --host 127.0.0.1 --port 8000
