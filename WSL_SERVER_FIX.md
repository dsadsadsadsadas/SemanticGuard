# WSL Server Connection Fix

## Problem

You're running the Trepan server in WSL, but the VS Code extension (running in Windows) can't connect to it. The status bar shows "Trepan ⚫" (offline) instead of "Trepan ✅" (online).

## Root Cause

The server is binding to `127.0.0.1` (localhost), which in WSL refers to the **WSL network interface**, not the Windows network interface. Windows can't reach `127.0.0.1:8000` in WSL.

## Solution 1: Bind to 0.0.0.0 (RECOMMENDED)

Run the server with `--host 0.0.0.0` to make it accessible from Windows:

```bash
# In WSL terminal
conda activate zero_point
python prepare_trepan_model.py && python start_server.py --host 0.0.0.0
```

This makes the server listen on **all network interfaces**, including the one Windows can reach.

## Solution 2: Use WSL IP Address

Find your WSL IP address and configure the extension to use it:

### Step 1: Find WSL IP

```bash
# In WSL terminal
ip addr show eth0 | grep "inet\b" | awk '{print $2}' | cut -d/ -f1
```

Example output: `172.24.123.45`

### Step 2: Start Server on 0.0.0.0

```bash
python start_server.py --host 0.0.0.0
```

### Step 3: Configure Extension

In VS Code settings (Windows side):

```json
{
  "trepan.serverUrl": "http://172.24.123.45:8000"
}
```

Replace `172.24.123.45` with your actual WSL IP.

## Solution 3: Use localhost.localdomain (WSL2 Only)

If you're using WSL2, Windows can access WSL services via `localhost`:

### Step 1: Start Server on 0.0.0.0

```bash
python start_server.py --host 0.0.0.0
```

### Step 2: Keep Default Extension Settings

The extension should work with default `http://127.0.0.1:8000` because WSL2 forwards localhost automatically.

## Verification Steps

### 1. Check Server is Running

In WSL terminal, you should see:

```
🛡️  Trepan Gatekeeper starting on http://0.0.0.0:8000
   Docs: http://0.0.0.0:8000/docs
```

### 2. Test from WSL

```bash
# In WSL terminal
curl http://localhost:8000/health
```

Expected output:
```json
{"status":"ok","model_loaded":true}
```

### 3. Test from Windows

Open PowerShell (Windows side):

```powershell
# Test with localhost (WSL2 only)
curl http://localhost:8000/health

# Or test with WSL IP
curl http://172.24.123.45:8000/health
```

Expected output:
```json
{"status":"ok","model_loaded":true}
```

### 4. Check Extension Status

In VS Code Extension Development Host:
- Look at status bar (bottom right)
- Should show: `$(shield) Trepan ✅`
- If still offline, check Developer Console (Help → Toggle Developer Tools)

## Troubleshooting

### Issue: "Connection Refused"

**Cause**: Server not running or firewall blocking.

**Fix**:
```bash
# Check if server is running
ps aux | grep uvicorn

# Check if port is listening
netstat -tuln | grep 8000
```

### Issue: "Trepan ⏳" (Loading Forever)

**Cause**: Model is still loading.

**Fix**: Wait 30-60 seconds for Llama 3.1 to load. Check WSL terminal for:
```
INFO:     Application startup complete.
```

### Issue: "Trepan ⚫" (Offline)

**Cause**: Extension can't reach server.

**Fix**:
1. Verify server is on `0.0.0.0`:
   ```bash
   python start_server.py --host 0.0.0.0
   ```

2. Test from Windows PowerShell:
   ```powershell
   curl http://localhost:8000/health
   ```

3. Check extension settings:
   ```json
   {
     "trepan.serverUrl": "http://127.0.0.1:8000"
   }
   ```

4. Check Developer Console for errors:
   - Help → Toggle Developer Tools
   - Look for `[TREPAN DEBUG]` messages

### Issue: WSL IP Changes

**Cause**: WSL IP is dynamic and changes on restart.

**Fix**: Use Solution 1 (bind to 0.0.0.0) and keep extension on `localhost`.

## Quick Start Script

Create `start_trepan_wsl.sh`:

```bash
#!/bin/bash
# Start Trepan server in WSL with proper network binding

echo "🛡️  Starting Trepan in WSL..."
echo ""

# Activate conda environment
conda activate zero_point

# Prepare model (if needed)
python prepare_trepan_model.py

# Start server on 0.0.0.0 for Windows access
python start_server.py --host 0.0.0.0 --port 8000

echo ""
echo "✅ Server accessible from Windows at http://localhost:8000"
```

Make it executable:
```bash
chmod +x start_trepan_wsl.sh
```

Run it:
```bash
./start_trepan_wsl.sh
```

## Network Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         WINDOWS                             │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  VS Code Extension (Extension Development Host)      │  │
│  │  Tries to connect to: http://127.0.0.1:8000         │  │
│  └────────────────────┬─────────────────────────────────┘  │
│                       │                                     │
│                       │ HTTP Request                        │
│                       ▼                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Windows Network Stack                               │  │
│  │  Forwards to WSL if server on 0.0.0.0               │  │
│  └────────────────────┬─────────────────────────────────┘  │
└───────────────────────┼─────────────────────────────────────┘
                        │
                        │ WSL Bridge
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                          WSL                                │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Trepan Server (FastAPI + Uvicorn)                   │  │
│  │  Listening on: 0.0.0.0:8000                          │  │
│  │  Accessible from Windows via localhost               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Expected Console Output

### WSL Terminal (Server)

```
🔍 Checking dependencies...

  ✅ FastAPI
  ✅ Uvicorn (server)
  ✅ Transformers
  ✅ PyTorch
  ✅ PEFT (adapters)

✅ Core server deps OK — soft failures handled at runtime.

🛡️  Trepan Gatekeeper starting on http://0.0.0.0:8000
   Docs: http://0.0.0.0:8000/docs
   Press Ctrl+C to stop.

================================================================================
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### VS Code Developer Console (Extension)

```
[TREPAN DEBUG] Checking server health...
[TREPAN DEBUG] Server response: {"status":"ok","model_loaded":true}
[TREPAN DEBUG] Server is ONLINE
🛡️ Trepan Gatekeeper: Airbag active
```

### VS Code Status Bar

```
$(shield) Trepan ✅
```

## Summary

**The Fix**: Run server with `--host 0.0.0.0` instead of default `127.0.0.1`

```bash
# In WSL
conda activate zero_point
python prepare_trepan_model.py && python start_server.py --host 0.0.0.0
```

This makes the server accessible from Windows while keeping the extension configured to use `http://127.0.0.1:8000`.

---

**Status**: This is a common WSL networking issue. The fix is simple and works reliably! 🛡️✅
