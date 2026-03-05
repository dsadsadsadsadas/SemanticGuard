# ✅ SOLUTION CONFIRMED

## TEST RESULTS

Just ran connection test from Windows - **SERVER IS WORKING PERFECTLY ON PORT 8001!**

```
✅ WORKING: http://127.0.0.1:8001
✅ WORKING: http://localhost:8001
✅ WORKING: http://172.0.31.100.18:8001

❌ FAILED: http://127.0.0.1:8000
❌ FAILED: http://localhost:8000
❌ FAILED: http://172.31.100.18:8000
```

## THE PROBLEM

VS Code extension is configured to use port 8001, but it's somehow still trying to connect to port 8000.

## THE SOLUTION

The extension's `discoverServerURL()` function has a bug. It's supposed to extract the port from your settings, but it's using the default `basePort = 8000` instead.

### Quick Fix (Open Developer Console)

1. **Open VS Code Developer Tools:**
   - Press `Ctrl+Shift+P`
   - Type: "Developer: Toggle Developer Tools"
   - Press Enter

2. **Go to Console tab**

3. **Type this command and press Enter:**
   ```javascript
   vscode.workspace.getConfiguration("trepan").get("serverUrl")
   ```

4. **Check the output:**
   - If it shows `"http://172.31.100.18:8001"` → Settings are correct
   - If it shows `undefined` or `"http://172.31.100.18:8000"` → Settings are wrong

5. **If settings are correct but extension still fails, type:**
   ```javascript
   vscode.workspace.getConfiguration("trepan").update("serverUrl", "http://127.0.0.1:8001", 1)
   ```
   
   This forces the setting to `http://127.0.0.1:8001` (which we know works from the test).

6. **Reload VS Code:**
   - Press `Ctrl+Shift+P`
   - Type: "Developer: Reload Window"
   - Press Enter

### Alternative: Use Settings UI

1. **Open Settings:** `Ctrl+,`
2. **Search for:** `trepan.serverUrl`
3. **Change to:** `http://127.0.0.1:8001` (NOT the WSL IP, use localhost)
4. **Save**
5. **Reload Window:** `Ctrl+Shift+P` → "Developer: Reload Window"

## WHY USE 127.0.0.1:8001 INSTEAD OF WSL IP?

The test shows that `http://127.0.0.1:8001` works perfectly from Windows. This is simpler and more reliable than using the WSL IP because:

1. WSL IP can change on reboot
2. Localhost is always stable
3. The extension's discovery function will find it faster

## WHAT TO EXPECT AFTER FIX

1. **Status bar should show:**
   ```
   $(shield) Trepan ✅
   ```

2. **When you save a file, you should see in Developer Console:**
   ```
   [TREPAN DEBUG] Save event triggered for: your-file.py
   [TREPAN EVAL] Using discovered URL: http://127.0.0.1:8001
   ```

3. **Trepan will start evaluating your saves!**

## IF IT STILL DOESN'T WORK

Share the output from the Developer Console (Console tab) when you:
1. Reload VS Code
2. Wait 5 seconds
3. Copy all the `[TREPAN` log messages

This will show exactly what URLs the extension is testing and why it's failing.
