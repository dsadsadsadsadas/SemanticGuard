# FORCE EXTENSION REFRESH - EASIEST FIX

## Problem
VS Code extension is showing old cached server URL (port 8000) instead of new URL (port 8001).

## EASIEST Solution

1. **Open Command Palette**: `Ctrl+Shift+P`
2. **Type**: "Developer: Reload Window"
3. **Press Enter**

This will:
- Reload the entire VS Code window
- Force the extension to re-read your updated settings
- Re-discover the server at the correct URL (port 8001)

## Alternative (if reload doesn't work)

1. **Disable Trepan Extension**:
   - `Ctrl+Shift+X` (Extensions)
   - Find "Trepan"
   - Click "Disable"

2. **Enable Trepan Extension**:
   - Click "Enable"

3. **Check Status**:
   - Should now show correct port 8001

## Verify Success
After reload, you should see:
```
🛡️ Trepan Gatekeeper Server: http://172.31.100.18:8001 Airbag: ARMED ✅ Server: online
```

And Trepan will respond to file saves.