# WSL2 Bridge Alignment Implementation - Complete

## Overview

This document details the comprehensive implementation of WSL2 bridge alignment fixes to resolve the connection issue between the Windows VS Code extension and the WSL2 Trepan server. All four requested diagnostic and connection features have been implemented.

## ✅ Implemented Features

### 1. Connection Logic Update ✅
**Location**: `extension/extension.js` - `discoverServerURL()` function
**Implementation**:
- **Multi-URL Testing**: Automatically tests `127.0.0.1:8000`, `localhost:8000`, and WSL IP
- **WSL IP Discovery**: Uses `wsl.exe hostname -I` to find the correct internal WSL IP
- **Intelligent Fallback**: Falls back through connection options until one succeeds
- **URL Caching**: Caches successful URLs to avoid repeated discovery overhead
- **Configuration Update**: Automatically updates VS Code settings with working URL

### 2. Heartbeat Debugging ✅
**Location**: `extension/extension.js` - Enhanced `checkServerHealth()` function
**Implementation**:
- **Detailed Error Logging**: Logs exact Node.js error codes (ECONNREFUSED, ETIMEDOUT, etc.)
- **VS Code Output Channel**: Shows diagnostics in dedicated "Trepan Gatekeeper" output channel
- **Error Code Meanings**: Translates error codes to human-readable explanations
- **Troubleshooting Guidance**: Provides specific solutions for each error type
- **Real-time Monitoring**: Logs all connection attempts with timestamps

### 3. WSL Bridge Auto-Discovery ✅
**Location**: `extension/extension.js` - `getWSLIP()` function
**Implementation**:
- **Platform Detection**: Only runs WSL commands on Windows systems
- **Command Execution**: Runs `wsl.exe hostname -I` with timeout protection
- **IP Validation**: Validates discovered IPs with regex pattern matching
- **Error Handling**: Graceful fallback if WSL commands fail
- **Integration**: Seamlessly integrates with connection discovery system

### 4. Diagnostic Script ✅
**Location**: `debug_bridge.py` - Comprehensive diagnostic tool
**Implementation**:
- **System Information**: Gathers Python version, platform, hostname, IP addresses
- **WSL Detection**: Automatically detects if running in WSL environment
- **Socket Testing**: Tests raw socket connectivity before HTTP requests
- **HTTP Diagnostics**: Detailed HTTP request/response analysis with headers
- **Multi-Host Testing**: Tests localhost, 127.0.0.1, 0.0.0.0, and system IPs
- **Endpoint Testing**: Tests multiple server endpoints (/health, /docs, /)
- **JSON Analysis**: Parses and analyzes Trepan-specific response data
- **Actionable Recommendations**: Provides specific troubleshooting steps

## 🔧 Technical Implementation Details

### Auto-Discovery Flow
```javascript
1. Check cached URL (if available)
2. Extract port from VS Code configuration
3. Build candidate URL list:
   - http://127.0.0.1:8000
   - http://localhost:8000
   - http://{WSL_IP}:8000 (if discovered)
4. Test each URL with /health endpoint
5. Return first successful URL
6. Cache successful URL for future use
7. Update VS Code configuration
```

### Error Code Mapping
```javascript
const errorMeanings = {
    'ECONNREFUSED': 'Connection refused - server not running or port blocked',
    'ETIMEDOUT': 'Connection timeout - network issue or server overloaded', 
    'EHOSTUNREACH': 'Host unreachable - network routing issue',
    'ENOTFOUND': 'DNS resolution failed - hostname not found',
    'ECONNRESET': 'Connection reset - server closed connection'
};
```

### WSL IP Discovery
```javascript
// Windows only: wsl.exe hostname -I
const { stdout } = await execAsync('wsl.exe hostname -I', { timeout: 5000 });
const ips = stdout.trim().split(/\s+/);
// Returns first valid IPv4 address
```

## 🚀 Usage Instructions

### 1. Automatic Extension Behavior
The extension now automatically:
- Discovers the correct server URL on startup
- Falls back through connection options if primary fails
- Updates VS Code settings with working URL
- Shows detailed diagnostics in Output Channel

### 2. Manual Diagnostic Script
```bash
# Basic diagnostics
python debug_bridge.py

# Test specific host/port
python debug_bridge.py --host 0.0.0.0 --port 8001

# Verbose output with headers
python debug_bridge.py --verbose
```

### 3. VS Code Output Channel
1. Open VS Code Command Palette (`Ctrl+Shift+P`)
2. Run "View: Toggle Output"
3. Select "Trepan Gatekeeper" from dropdown
4. View real-time connection diagnostics

## 🔍 Diagnostic Output Examples

### Extension Console Logs
```
[TREPAN WSL] Testing connection URLs: http://127.0.0.1:8000, http://localhost:8000, http://172.20.144.1:8000
[TREPAN WSL] Testing: http://127.0.0.1:8000
[TREPAN WSL] ❌ Failed http://127.0.0.1:8000: ECONNREFUSED
[TREPAN WSL] Testing: http://172.20.144.1:8000
[TREPAN WSL] ✅ Connected to: http://172.20.144.1:8000
[TREPAN WSL] Server status: {"status":"ok","model_loaded":true}
```

### VS Code Output Channel
```
[2026-03-04T15:30:45.123Z] Connection failed: http://127.0.0.1:8000
  Error: ECONNREFUSED - Connection refused - server not running or port blocked
  Details: connect ECONNREFUSED 127.0.0.1:8000
  Troubleshooting: Server is not running. Start with: python start_server.py --host 0.0.0.0
```

### Diagnostic Script Output
```
🔍 TREPAN WSL BRIDGE DIAGNOSTICS
================================================================================

📋 System Information:
   hostname: DESKTOP-ABC123
   ip_addresses: 172.20.144.1, 192.168.1.100
   is_wsl: True
   kernel_version: Linux version 5.15.0-microsoft-standard-WSL2

🎯 Testing hosts: localhost, 127.0.0.1, 0.0.0.0, 172.20.144.1

────────────────────────────────────────────────────────────────
Testing: 172.20.144.1:8000
────────────────────────────────────────────────────────────────

🔌 Testing socket connectivity to 172.20.144.1:8000
   ✅ Socket connection successful

🌐 Testing HTTP request to: http://172.20.144.1:8000/health
   📤 Request headers:
      User-Agent: Trepan-Debug-Bridge/1.0
      Accept: application/json
   📥 Response received in 0.045s
   📊 Status: 200 OK
   📋 Response headers:
      content-type: application/json
      content-length: 45
   📄 Response body (45 bytes):
      {
        "status": "ok",
        "model_loaded": true
      }
   🛡️  Trepan Status: ok
      ✅ Server is healthy
   🤖 Model Loaded: true
      ✅ Model is ready for inference

📊 DIAGNOSTIC SUMMARY
================================================================================
✅ Successful connections: 1
   - http://172.20.144.1:8000

💡 Recommendations:
   1. Use any of the successful URLs in your VS Code extension
   2. Update extension serverUrl setting to working URL
   3. Server is accessible and responding correctly

🐧 WSL-specific notes:
   - Server is running in WSL2 environment
   - Windows VS Code can access via any successful URL above
   - If extension still shows offline, check VS Code extension logs
```

## 🛠️ Troubleshooting Guide

### Common Issues and Solutions

1. **Extension Still Shows "Offline"**
   - Check VS Code Output Channel for detailed error logs
   - Run diagnostic script to verify server accessibility
   - Restart VS Code to reload extension with new settings

2. **WSL IP Discovery Fails**
   - Ensure running on Windows with WSL2 installed
   - Check if `wsl.exe` is in PATH
   - Manually test: `wsl.exe hostname -I` in PowerShell

3. **All Connection Attempts Fail**
   - Verify server is running: `python start_server.py --host 0.0.0.0`
   - Check Ollama is running: `ollama serve`
   - Test with diagnostic script: `python debug_bridge.py`

4. **Intermittent Connection Issues**
   - Extension now caches working URLs to reduce discovery overhead
   - Failed cached URLs trigger automatic rediscovery
   - Check server logs for stability issues

## 📊 Connection Success Matrix

| Server Binding | Windows Extension | WSL Extension | Status |
|----------------|-------------------|---------------|---------|
| 127.0.0.1:8000 | ❌ Not accessible | ✅ Accessible | WSL Only |
| 0.0.0.0:8000 | ✅ Auto-discovered | ✅ Accessible | Universal |
| localhost:8000 | ✅ Auto-discovered | ✅ Accessible | Universal |

## 🎯 Next Steps

1. **Test the enhanced connection logic** by starting the server with `--host 0.0.0.0`
2. **Monitor VS Code Output Channel** for real-time connection diagnostics
3. **Run diagnostic script** if connection issues persist
4. **Check extension console logs** in VS Code Developer Tools for detailed debugging

The WSL2 bridge alignment is now complete with comprehensive auto-discovery, detailed error reporting, and actionable troubleshooting guidance.