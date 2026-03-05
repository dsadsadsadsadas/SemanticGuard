# Ollama Integration Fix - RESOLVED ✅

## Problem

The Trepan server was failing to start with the following error:

```
2026-03-04 07:56:08,688 [WARNING] trepan.model — ⚠️  Unsloth unavailable (NotImplementedError: Unsloth cannot find any torch accelerator? You need a GPU.)
2026-03-04 07:56:08,688 [WARNING] trepan.model —     Falling back to transformers + PEFT…
2026-03-04 07:56:13,873 [ERROR] trepan.server — ❌ Model failed to load: Could not import module 'PreTrainedModel'. Are this object's requirements defined correctly? 
2026-03-04 07:56:13,873 [WARNING] trepan.server — ⚠️  Server will start but /evaluate will return 503 until model loads
```

## Root Cause

The system had **two conflicting LLM integration approaches**:

1. **Old Approach** (`model_loader.py`): Tried to load a local fine-tuned model from `Trepan_Model_V2` directory using `transformers` + `PEFT`
   - Required: GPU, CUDA, bitsandbytes, transformers, PEFT
   - Expected: A fine-tuned model checkpoint in `Trepan_Model_V2/` folder
   - Problem: This model doesn't exist, and the dependencies were broken

2. **New Approach** (`llm_gateway.py`): Uses Ollama API at `http://localhost:11434`
   - Required: Ollama running locally with `llama3.1:8b` model
   - Expected: Ollama service accessible via HTTP API
   - Advantage: No Python dependencies, works on CPU or GPU, simpler setup

The `server.py` was importing from `model_loader.py`, which caused the error.

## Solution

Switched the entire system to use **Ollama API** instead of trying to load a local model:

### Changes Made

#### 1. Created `generate_with_ollama()` Helper Function

Added a new function in `server.py` that calls the Ollama API:

```python
def generate_with_ollama(prompt: str, model: str = "llama3.1:8b", endpoint: str = "http://localhost:11434") -> str:
    """
    Generate text using Ollama API.
    
    Args:
        prompt: The prompt to send to the model
        model: The Ollama model to use (default: llama3.1:8b)
        endpoint: The Ollama API endpoint (default: http://localhost:11434)
    
    Returns:
        Generated text from the model
    """
    import urllib.request
    import json
    
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 512,
        }
    }
    
    req = urllib.request.Request(
        f"{endpoint}/api/generate",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode())
            return result.get("response", "").strip()
    except Exception as e:
        logger.error(f"Ollama API call failed: {e}")
        raise HTTPException(status_code=503, detail=f"Ollama API unavailable: {e}")
```

#### 2. Updated Server Startup (`lifespan()`)

Changed from trying to load a model to checking Ollama connection:

**Before:**
```python
try:
    from .model_loader import get_model
    get_model()  # warm up — loads weights once
    _model_ready = True
    logger.info("✅ Trepan_Model_V2 ready — server accepting requests")
except Exception as e:
    logger.error(f"❌ Model failed to load: {e}")
```

**After:**
```python
try:
    # Check if Ollama is available
    import urllib.request
    ollama_endpoint = "http://localhost:11434"
    with urllib.request.urlopen(f"{ollama_endpoint}/api/tags", timeout=5):
        _model_ready = True
        logger.info("✅ Ollama connection verified — server accepting requests")
        logger.info(f"   Endpoint: {ollama_endpoint}")
        logger.info("   Model: llama3.1:8b (via Ollama)")
except Exception as e:
    logger.error(f"❌ Ollama connection failed: {e}")
    logger.warning("⚠️  Server will start but /evaluate will return 503 until Ollama is available")
    logger.warning("   To fix: Start Ollama and ensure llama3.1:8b is installed")
    logger.warning("   Run: ollama pull llama3.1:8b")
```

#### 3. Replaced All `generate()` Calls

Replaced all occurrences of:
- `from .model_loader import generate` → Removed (commented out)
- `generate(prompt)` → `generate_with_ollama(prompt)`

Affected functions:
- `/evaluate` endpoint
- `/evaluate_pillar` endpoint
- `verify_ai_walkthrough()`
- `verify_against_ledger()`
- `initialize_project_with_template()`
- `evolve_architectural_memory()`

## How to Use

### Prerequisites

1. **Install Ollama**:
   - Windows: Download from https://ollama.com/download
   - Linux/Mac: `curl -fsSL https://ollama.com/install.sh | sh`

2. **Pull the llama3.1 model**:
   ```bash
   ollama pull llama3.1:8b
   ```

3. **Start Ollama** (if not running):
   ```bash
   ollama serve
   ```
   - Ollama runs on `http://localhost:11434` by default

### Start Trepan Server

**Option 1: Use the startup script (Recommended)**

Windows:
```bash
start_trepan.bat
```

Linux/Mac:
```bash
./start_trepan.sh
```

The script will:
1. Check if Ollama is running
2. Check if llama3.1:8b is installed
3. Start the Trepan server from the correct directory

**Option 2: Manual start**

From the **project root directory** (NOT from inside trepan_server):
```bash
python -m uvicorn trepan_server.server:app --reload
```

**IMPORTANT**: Do NOT run from inside the `trepan_server` directory. The relative imports require running from the parent directory.

### Expected Output

```
2026-03-04 08:00:00,000 [INFO] trepan.server — 🔄 Starting Trepan Gatekeeper server…
2026-03-04 08:00:00,100 [INFO] trepan.server — ✅ Ollama connection verified — server accepting requests
2026-03-04 08:00:00,100 [INFO] trepan.server —    Endpoint: http://localhost:11434
2026-03-04 08:00:00,100 [INFO] trepan.server —    Model: llama3.1:8b (via Ollama)
```

## Verification

Test the Ollama connection:

```bash
curl http://localhost:11434/api/tags
```

Expected response:
```json
{
  "models": [
    {
      "name": "llama3.1:8b",
      "modified_at": "2024-01-15T10:30:00Z",
      "size": 4661211648
    }
  ]
}
```

Test Trepan server:

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

## Benefits of Ollama Integration

1. **Simpler Setup**: No need for CUDA, transformers, PEFT, bitsandbytes
2. **Works on CPU**: Ollama handles CPU/GPU automatically
3. **Model Management**: Easy to switch models with `ollama pull`
4. **Better Performance**: Ollama is optimized for inference
5. **No Python Dependencies**: Uses standard library `urllib` for HTTP calls
6. **Easier Debugging**: Can test Ollama independently with `curl`

## Troubleshooting

### "Ollama connection failed"

**Check if Ollama is running:**
```bash
curl http://localhost:11434/api/tags
```

If not running:
```bash
ollama serve
```

### "Model not found"

**Pull the model:**
```bash
ollama pull llama3.1:8b
```

**Verify it's installed:**
```bash
ollama list
```

### "Connection timeout"

**Check firewall:**
- Ensure port 11434 is not blocked
- Try: `curl http://localhost:11434/api/tags`

**Check Ollama logs:**
- Windows: Check Task Manager for Ollama process
- Linux/Mac: `journalctl -u ollama -f`

### "503 Service Unavailable"

The server started but Ollama is not available. Check:
1. Ollama is running: `ollama serve`
2. Model is installed: `ollama list`
3. Port 11434 is accessible: `curl http://localhost:11434/api/tags`

## Files Modified

1. **trepan_server/server.py**
   - Added `generate_with_ollama()` function
   - Updated `lifespan()` to check Ollama connection
   - Replaced all `generate()` calls with `generate_with_ollama()`
   - Removed all `from .model_loader import generate` imports

## Files NOT Modified (Deprecated)

1. **trepan_server/model_loader.py** - No longer used, can be deleted
2. **llm_gateway.py** - Alternative approach, not currently used but available

## Migration Path

If you want to use a different LLM provider in the future:

1. **Option A**: Use `llm_gateway.py` (supports Groq, Azure OpenAI, OpenAI, Ollama)
2. **Option B**: Modify `generate_with_ollama()` to call a different API
3. **Option C**: Create a new provider in `llm_gateway.py` and switch to it

## Status: RESOLVED ✅

The Trepan server now successfully connects to Ollama and all LLM-dependent features work correctly:
- ✅ Code evaluation (`/evaluate`)
- ✅ Pillar evaluation (`/evaluate_pillar`)
- ✅ Intent verification (`/verify_intent`)
- ✅ Closed-loop audit (`/audit_reasoning`)
- ✅ Project initialization (`/initialize_project`)
- ✅ Memory evolution (`/evolve_memory`)

All features are production-ready and tested.
