# 🔍 FINAL DIAGNOSIS: PORT MISMATCH MYSTERY

## THE SITUATION

**What You Did:**
1. Closed VS Code completely
2. Started server in WSL: `python start_server.py --host 0.0.0.0 --port 8001`
3. Server started successfully on `http://0.0.0.0:8001`
4. VS Code settings show: `http://172.31.100.18:8001`
5. But extension displays: `http://172.31.100.18:8000` (WRONG PORT!)

**Terminal Output Shows:**
```
✅ Server startup complete - ready to accept requests
🛡️  Trepan Gatekeeper starting on http://0.0.0.0:8001
```

**VS Code Shows:**
```
Trepan: Server Url
URL of the Trepan inference server: http://172.31.100.18:8001  ← CORRECT

🛡️ Trepan Gatekeeper Server: http://172.31.100.18:8000  ← WRONG!
Airbag: ARMED ✅
Server: offline
```

## ROOT CAUSE ANALYSIS

### Issue #1: Extension's `discoverServerURL()` Function is Broken

The function extracts the port from your VS Code settings:

```javascript
const configuredUrl = cfg.get("serverUrl") ?? `http://127.0.0.1:${basePort}`;

// Extract port from configured URL
const urlMatch = configuredUrl.match(/:(\d+)/);
const port = urlMatch ? parseInt(urlMatch[1]) : basePort;
```

**Problem:** Even though your settings say `http://172.31.100.18:8001`, the function is somehow extracting port 8000 instead of 8001.

**Possible causes:**
1. VS Code settings cache not refreshing
2. The regex is matching the wrong port
3. There's a fallback to `basePort = 8000` happening somewhere

### Issue #2: The Message Format Doesn't Match Extension Code

The message `🛡️ Trepan Gatekeeper Server: http://172.31.100.18:8000` does NOT appear anywhere in `extension/extension.js`. This means:

1. It's coming from a different file
2. It's coming from VS Code's own UI
3. It's coming from a cached/old version of the extension

### Issue #3: Settings Not Being Read Correctly

The extension reads settings like this:

```javascript
const cfg = vscode.workspace.getConfiguration("trepan");
const serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8000";
```

If `cfg.get("serverUrl")` returns `null` or `undefined`, it falls back to `http://127.0.0.1:8000`.

## THE FIX

### Step 1: Verify VS Code Settings File Directly

Open your workspace settings file:
- Press `Ctrl+Shift+P`
- Type "Preferences: Open Workspace Settings (JSON)"
- Look for the `trepan.serverUrl` entry

It should look like:
```json
{
  "trepan.serverUrl": "http://172.31.100.18:8001"
}
```

If it says port 8000, change it to 8001 and save.

### Step 2: Clear Extension Cache

The extension might be caching the old URL in the `discoveredServerUrl` variable.

**Solution:** Add a manual override in the extension code to force it to use the correct URL.

### Step 3: Debug the Discovery Function

The `discoverServerURL()` function needs to be fixed to properly extract the port from your settings.

## QUICK FIX (NO CODE CHANGES)

Since you want NO code changes, here's what to do:

### Option A: Use Port 8000 Instead

1. **Stop your WSL server** (`Ctrl+C`)
2. **Wait 2 minutes** for Windows to clear the zombie connections
3. **Restart on port 8000:**
   ```bash
   python start_server.py --host 0.0.0.0 --port 8000
   ```
4. **Update VS Code settings to:**
   ```
   http://172.31.100.18:8000
   ```
5. **Reload VS Code**

### Option B: Force Extension to See Port 8001

1. **Open VS Code Developer Tools:**
   - Press `Ctrl+Shift+P`
   - Type "Developer: Toggle Developer Tools"
   - Press Enter

2. **Go to Console tab**

3. **Look for these log messages:**
   ```
   [TREPAN WSL] Testing connection URLs: ...
   [TREPAN WSL] Testing: http://172.31.100.18:8001
   [TREPAN WSL] ✅ Connected to: http://172.31.100.18:8001
   ```

4. **If you see:**
   ```
   [TREPAN WSL] Testing: http://172.31.100.18:8000
   [TREPAN WSL] ❌ Failed http://172.31.100.18:8000
   ```
   
   This confirms the extension is testing port 8000 instead of 8001.

5. **Check what `cfg.get("serverUrl")` returns:**
   - In the Console, type:
     ```javascript
     vscode.workspace.getConfiguration("trepan").get("serverUrl")
     ```
   - Press Enter
   - It should return: `"http://172.31.100.18:8001"`
   - If it returns `undefined` or `"http://172.31.100.18:8000"`, your settings aren't being read

### Option C: Nuclear Option - Reinstall Extension

1. **Uninstall Trepan extension completely**
2. **Close VS Code**
3. **Delete extension cache:**
   - Windows: `%USERPROFILE%\.vscode\extensions\`
   - Look for `trepan-gatekeeper-*` folder and delete it
4. **Reopen VS Code**
5. **Reinstall extension from VSIX or marketplace**
6. **Configure settings fresh:**
   ```json
   {
     "trepan.serverUrl": "http://172.31.100.18:8001",
     "trepan.enabled": true
   }
   ```

## WHAT TO CHECK IN DEVELOPER CONSOLE

Open Developer Tools (`Ctrl+Shift+P` → "Developer: Toggle Developer Tools") and look for:

1. **Health check logs:**
   ```
   [TREPAN HEALTH] Starting health check...
   [TREPAN WSL] Testing connection URLs: ...
   ```

2. **What URLs are being tested:**
   ```
   [TREPAN WSL] Testing: http://127.0.0.1:8001
   [TREPAN WSL] Testing: http://localhost:8001
   [TREPAN WSL] Testing: http://172.31.100.18:8001
   ```

3. **Connection results:**
   ```
   [TREPAN WSL] ✅ Connected to: http://172.31.100.18:8001
   ```
   OR
   ```
   [TREPAN WSL] ❌ Failed http://172.31.100.18:8001: ECONNREFUSED
   ```

## EXPECTED BEHAVIOR

When working correctly, you should see:

1. **In Developer Console:**
   ```
   [TREPAN HEALTH] Starting health check...
   [TREPAN WSL] Testing connection URLs: http://127.0.0.1:8001, http://localhost:8001, http://172.31.100.18:8001
   [TREPAN WSL] Testing: http://127.0.0.1:8001
   [TREPAN WSL] ❌ Failed http://127.0.0.1:8001: ECONNREFUSED
   [TREPAN WSL] Testing: http://localhost:8001
   [TREPAN WSL] ❌ Failed http://localhost:8001: ECONNREFUSED
   [TREPAN WSL] Testing: http://172.31.100.18:8001
   [TREPAN WSL] ✅ Connected to: http://172.31.100.18:8001
   [TREPAN HEALTH] ✅ Server response: {"status":"ok","model_loaded":true}
   ```

2. **In VS Code Status Bar:**
   ```
   $(shield) Trepan ✅
   ```

3. **When you save a file:**
   ```
   [TREPAN DEBUG] Save event triggered for: /path/to/file.py
   [TREPAN EVAL] Using discovered URL: http://172.31.100.18:8001
   ```

## NEXT STEPS

1. Open Developer Tools and check the console logs
2. Share what you see in the console when the extension activates
3. Check if the extension is testing port 8001 or port 8000
4. If it's testing port 8000, we know the settings aren't being read correctly
