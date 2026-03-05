# Quick Fix: Trepan Not Showing Online in WSL

## The Problem

You're running:
```bash
python prepare_trepan_model.py && python start_server.py
```

But VS Code Extension shows: `$(shield) Trepan ⚫` (offline)

## The Fix (30 seconds)

### Step 1: Stop Current Server

Press `Ctrl+C` in WSL terminal

### Step 2: Restart with Correct Host

```bash
conda activate zero_point
python prepare_trepan_model.py && python start_server.py --host 0.0.0.0
```

### Step 3: Verify

You should see:
```
🛡️  Trepan Gatekeeper starting on http://0.0.0.0:8000
```

### Step 4: Check Extension

Wait 5-10 seconds, then check VS Code status bar:
- Should change from `⚫` to `✅`

## Why This Works

- **Problem**: Server on `127.0.0.1` in WSL is not accessible from Windows
- **Solution**: Server on `0.0.0.0` listens on all interfaces, including the one Windows can reach
- **Result**: Extension can connect via `http://localhost:8000`

## Diagnostic Commands

### In WSL (check server)

```bash
# Check if server is running
ps aux | grep uvicorn

# Check if port is listening
netstat -tuln | grep 8000

# Test from WSL
curl http://localhost:8000/health
```

### In Windows PowerShell (check connection)

```powershell
# Test connection from Windows
curl http://localhost:8000/health
```

Expected output:
```json
{"status":"ok","model_loaded":true}
```

## Automated Diagnostic

Run this in WSL:
```bash
bash test_wsl_connection.sh
```

## Permanent Fix

Create `start_trepan_wsl.sh`:

```bash
#!/bin/bash
conda activate zero_point
python prepare_trepan_model.py && python start_server.py --host 0.0.0.0
```

Then just run:
```bash
bash start_trepan_wsl.sh
```

## Status Indicators

| Icon | Meaning | Action |
|------|---------|--------|
| `$(shield) Trepan ⚫` | Offline | Check server is running on 0.0.0.0 |
| `$(shield) Trepan ⏳` | Loading | Wait for model to load (30-60s) |
| `$(shield) Trepan ✅` | Online | Ready to use! |

---

**TL;DR**: Add `--host 0.0.0.0` to your start command! 🛡️
