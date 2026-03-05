# Trepan Not Responding to Saves - Debug Checklist

## 🔍 Step 1: Check Extension Status

1. **VS Code Status Bar**: Look at the bottom-right corner for the Trepan shield icon
   - ✅ `$(shield) Trepan ✅` = Online and working
   - ⏳ `$(shield) Trepan ⏳` = Server online, model loading
   - ⚫ `$(shield) Trepan ⚫` = Offline (this is likely your issue)
   - 🔄 `$(shield) Trepan 🔄` = Currently evaluating

2. **Click the Trepan Status**: Click the shield icon to see detailed status

## 🔍 Step 2: Check VS Code Output Channel

1. Open Command Palette (`Ctrl+Shift+P`)
2. Type "View: Toggle Output"
3. Select "Trepan Gatekeeper" from the dropdown
4. Look for connection error messages

## 🔍 Step 3: Check Extension Console Logs

1. Open VS Code Developer Tools (`Help → Toggle Developer Tools`)
2. Go to Console tab
3. Look for `[TREPAN]` log messages
4. Check for any error messages

## 🔍 Step 4: Verify Extension is Installed and Enabled

1. Go to Extensions view (`Ctrl+Shift+X`)
2. Search for "Trepan"
3. Verify it's installed and enabled
4. Check if it needs to be reloaded

## 🔍 Step 5: Test Server Connection

Run the diagnostic script:
```bash
python debug_bridge.py
```

## 🔍 Step 6: Check Extension Configuration

1. Open Settings (`Ctrl+,`)
2. Search for "trepan"
3. Check these settings:
   - `trepan.enabled`: Should be `true`
   - `trepan.serverUrl`: Should be correct server URL
   - `trepan.timeoutMs`: Should be reasonable (30000)

## 🔧 Common Fixes

### Fix 1: Extension Not Loaded
- Reload VS Code window (`Ctrl+Shift+P` → "Developer: Reload Window")

### Fix 2: Server Connection Issue
- Start server with: `python start_server.py --host 0.0.0.0`
- Check if Ollama is running: `ollama serve`

### Fix 3: Extension Disabled
- Enable in Extensions view
- Check if workspace has extension disabled

### Fix 4: Wrong Workspace
- Trepan only works in workspaces with `.trepan/` folder
- Open the correct project folder

### Fix 5: File Type Not Monitored
- Trepan only monitors code files (not .md, .txt, etc.)
- Try saving a .py, .js, .ts, or .java file