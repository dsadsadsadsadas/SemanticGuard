# Trepan Quick Start Guide

## Prerequisites

1. **Python 3.10 or 3.11** installed
2. **Ollama** installed and running
3. **llama3.1:8b** model downloaded

## Installation Steps

### 1. Install Ollama

**Windows:**
- Download from https://ollama.com/download
- Run the installer
- Ollama will start automatically

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Mac:**
```bash
brew install ollama
```

### 2. Pull the llama3.1 Model

```bash
ollama pull llama3.1:8b
```

This will download ~4.7GB. Wait for it to complete.

### 3. Verify Ollama is Running

```bash
curl http://localhost:11434/api/tags
```

You should see a JSON response with the llama3.1 model listed.

### 4. Install Python Dependencies

```bash
pip install fastapi uvicorn pydantic
```

Or if you have a requirements.txt:
```bash
pip install -r trepan_server/requirements.txt
```

## Starting Trepan

### Easy Way (Recommended)

**Windows:**
```bash
start_trepan.bat
```

**Linux/Mac:**
```bash
./start_trepan.sh
```

The script will check everything and start the server automatically.

### Manual Way

From the **project root directory**:
```bash
python -m uvicorn trepan_server.server:app --reload
```

**IMPORTANT**: Run from the project root, NOT from inside `trepan_server/`

## Verify It's Working

### 1. Check Server Health

```bash
curl http://127.0.0.1:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "model_loaded": true,
  "version": "2.0.0"
}
```

### 2. Test Code Evaluation

```bash
curl -X POST http://127.0.0.1:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "golden_state": "Use Python for backend",
    "system_rules": "No hardcoded secrets",
    "user_command": "def hello(): return \"world\""
  }'
```

You should get a response with `"action": "ACCEPT"` or `"action": "REJECT"`.

## Common Issues

### "ImportError: attempted relative import with no known parent package"

**Problem**: You're running from inside the `trepan_server` directory.

**Solution**: Run from the project root:
```bash
cd ..  # Go up one directory
python -m uvicorn trepan_server.server:app --reload
```

### "Ollama connection failed"

**Problem**: Ollama is not running.

**Solution**: Start Ollama:
```bash
ollama serve
```

Or on Windows, just start the Ollama app from the Start menu.

### "Model not found"

**Problem**: llama3.1:8b is not installed.

**Solution**: Pull the model:
```bash
ollama pull llama3.1:8b
```

### "Connection refused on port 8000"

**Problem**: Another service is using port 8000.

**Solution**: Use a different port:
```bash
python -m uvicorn trepan_server.server:app --reload --port 8001
```

### "503 Service Unavailable"

**Problem**: Server started but can't connect to Ollama.

**Solution**: 
1. Check Ollama is running: `curl http://localhost:11434/api/tags`
2. Check the model is installed: `ollama list`
3. Restart Ollama: `ollama serve`

## Next Steps

Once the server is running:

1. **Initialize a Project**:
   ```bash
   curl -X POST http://127.0.0.1:8000/initialize_project \
     -H "Content-Type: application/json" \
     -d '{
       "mode": "solo-indie",
       "project_path": "C:\\Users\\ethan\\Documents\\Projects\\Trepan_Test_Zone"
     }'
   ```

2. **View Available Templates**:
   ```bash
   curl http://127.0.0.1:8000/templates
   ```

3. **Test Memory Evolution**:
   ```bash
   python test_memory_evolution.py
   ```

## Documentation

- **OLLAMA_INTEGRATION_FIX.md** - Technical details about the Ollama integration
- **TASK_6_COMPLETION_SUMMARY.md** - Memory evolution feature documentation
- **USER_GUIDE_MEMORY_EVOLUTION.md** - User guide for memory evolution
- **5_PILLARS_EVOLUTION_DIAGRAM.md** - System architecture diagrams

## Getting Help

If you encounter issues:

1. Check the server logs in the terminal
2. Check Ollama logs: `ollama logs` (if available)
3. Verify all prerequisites are installed
4. Try the troubleshooting steps above

## Success Indicators

You'll know everything is working when you see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using StatReload
2026-03-04 08:00:00,000 [INFO] trepan.server — 🔄 Starting Trepan Gatekeeper server…
2026-03-04 08:00:00,100 [INFO] trepan.server — ✅ Ollama connection verified — server accepting requests
2026-03-04 08:00:00,100 [INFO] trepan.server —    Endpoint: http://localhost:11434
2026-03-04 08:00:00,100 [INFO] trepan.server —    Model: llama3.1:8b (via Ollama)
INFO:     Application startup complete.
```

Happy coding with Trepan! 🛡️
