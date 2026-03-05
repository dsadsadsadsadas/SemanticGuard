# 🚨 TREPAN NOT RESPONDING TO SAVES - QUICK FIX

## Problem Identified ✅

**Root Cause**: The Trepan server on port 8000 is in a crash loop. Every time it receives an HTTP request, it crashes immediately, leaving hundreds of dead connections.

**Evidence**:
- ✅ Port 8000 has a listening process (PID 4688)
- ❌ HTTP requests to /health fail with "Remote end closed connection"
- 🚨 Hundreds of CLOSE_WAIT/TIME_WAIT connections (crash loop signature)

## Immediate Solution 🔧

**Use Port 8001 Instead** (bypasses the crashed server on port 8000):

### Step 1: Start Server on Port 8001
```bash
python start_server.py --port 8001
```

### Step 2: Update VS Code Extension Settings
1. Open VS Code Settings (`Ctrl + ,`)
2. Search for "trepan"
3. Find "Trepan: Server Url"
4. Change from `http://127.0.0.1:8000` to `http://127.0.0.1:8001`

### Step 3: Test the Connection
```bash
curl http://localhost:8001/health
```

You should see:
```json
{"status":"ok","model_loaded":true}
```

## Why This Works

- Port 8001 is clean (no crashed processes)
- All dependencies are working correctly
- The server code itself is functional
- Only port 8000 has the crashed process holding it

## Alternative: Restart System

If you prefer to use port 8000:
1. Restart your computer (clears all network connections)
2. Start server normally: `python start_server.py`

## Verify Trepan is Working

After starting on port 8001:
1. **Check VS Code Status Bar**: Should show `$(shield) Trepan ✅`
2. **Save a code file**: Trepan should now intercept and evaluate saves
3. **Check VS Code Output Channel**: "Trepan Gatekeeper" should show connection logs

## Root Cause Fix (For Later)

The original crash was caused by a subprocess variable naming conflict in `start_server.py`. This has been fixed in the code, but the crashed process on port 8000 needs to be cleared by either:
- System restart
- Waiting for Windows to clean up the connections (2+ hours)
- Using port 8001 permanently