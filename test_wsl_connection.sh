#!/bin/bash
# Test WSL to Windows connection for Trepan server

echo "🔍 Trepan WSL Connection Diagnostic"
echo "===================================="
echo ""

# Test 1: Check if server is running
echo "Test 1: Check if server process is running"
if ps aux | grep -q "[u]vicorn"; then
    echo "✅ Uvicorn process found"
    ps aux | grep "[u]vicorn"
else
    echo "❌ Uvicorn process NOT found"
    echo "   Start server with: python start_server.py --host 0.0.0.0"
fi
echo ""

# Test 2: Check if port 8000 is listening
echo "Test 2: Check if port 8000 is listening"
if netstat -tuln 2>/dev/null | grep -q ":8000"; then
    echo "✅ Port 8000 is listening"
    netstat -tuln | grep ":8000"
elif ss -tuln 2>/dev/null | grep -q ":8000"; then
    echo "✅ Port 8000 is listening"
    ss -tuln | grep ":8000"
else
    echo "❌ Port 8000 is NOT listening"
    echo "   Start server with: python start_server.py --host 0.0.0.0"
fi
echo ""

# Test 3: Get WSL IP address
echo "Test 3: WSL IP Address"
WSL_IP=$(ip addr show eth0 2>/dev/null | grep "inet\b" | awk '{print $2}' | cut -d/ -f1)
if [ -n "$WSL_IP" ]; then
    echo "✅ WSL IP: $WSL_IP"
else
    echo "⚠️  Could not determine WSL IP"
fi
echo ""

# Test 4: Test localhost connection from WSL
echo "Test 4: Test connection from WSL (localhost)"
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Server responds on localhost"
    curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8000/health
else
    echo "❌ Server does NOT respond on localhost"
    echo "   Make sure server is running"
fi
echo ""

# Test 5: Test 0.0.0.0 binding
echo "Test 5: Check if server is bound to 0.0.0.0"
if netstat -tuln 2>/dev/null | grep ":8000" | grep -q "0.0.0.0"; then
    echo "✅ Server is bound to 0.0.0.0 (accessible from Windows)"
elif ss -tuln 2>/dev/null | grep ":8000" | grep -q "0.0.0.0"; then
    echo "✅ Server is bound to 0.0.0.0 (accessible from Windows)"
elif netstat -tuln 2>/dev/null | grep ":8000" | grep -q "127.0.0.1"; then
    echo "⚠️  Server is bound to 127.0.0.1 (NOT accessible from Windows)"
    echo "   Restart with: python start_server.py --host 0.0.0.0"
elif ss -tuln 2>/dev/null | grep ":8000" | grep -q "127.0.0.1"; then
    echo "⚠️  Server is bound to 127.0.0.1 (NOT accessible from Windows)"
    echo "   Restart with: python start_server.py --host 0.0.0.0"
else
    echo "❌ Could not determine server binding"
fi
echo ""

# Test 6: Instructions for Windows testing
echo "Test 6: Test from Windows PowerShell"
echo "Run this command in Windows PowerShell:"
echo ""
echo "  curl http://localhost:8000/health"
echo ""
echo "Expected output:"
echo '  {"status":"ok","model_loaded":true}'
echo ""

echo "===================================="
echo "Summary:"
echo "--------"
echo "1. Server should be running (uvicorn process)"
echo "2. Port 8000 should be listening"
echo "3. Server should be bound to 0.0.0.0 (not 127.0.0.1)"
echo "4. Test from Windows PowerShell should succeed"
echo ""
echo "If tests fail, restart server with:"
echo "  python start_server.py --host 0.0.0.0"
echo "===================================="
