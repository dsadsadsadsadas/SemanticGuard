#!/usr/bin/env python3
"""
🔍 Trepan WSL Bridge Diagnostic Script

This script tests the Trepan server connection from inside the WSL environment
and provides detailed diagnostics about network connectivity, response headers,
and server status. Use this to determine if connection issues are due to:

1. Server not running
2. Network/firewall issues  
3. Response format problems
4. WSL2 bridge configuration

Usage:
    python debug_bridge.py                    # Test default localhost:8000
    python debug_bridge.py --host 0.0.0.0    # Test all interfaces
    python debug_bridge.py --port 8001       # Test custom port
    python debug_bridge.py --verbose         # Show detailed headers
"""

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime


def get_system_info():
    """Gather system and network information"""
    info = {
        'timestamp': datetime.now().isoformat(),
        'python_version': sys.version,
        'platform': sys.platform,
    }
    
    try:
        # Get hostname
        info['hostname'] = socket.gethostname()
        
        # Get IP addresses
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        if result.returncode == 0:
            info['ip_addresses'] = result.stdout.strip().split()
        
        # Check if we're in WSL
        try:
            with open('/proc/version', 'r') as f:
                version = f.read()
                info['is_wsl'] = 'microsoft' in version.lower() or 'wsl' in version.lower()
                info['kernel_version'] = version.strip()
        except:
            info['is_wsl'] = False
            
    except Exception as e:
        info['system_info_error'] = str(e)
    
    return info


def test_port_connectivity(host, port):
    """Test if a port is reachable via socket connection"""
    print(f"\n🔌 Testing socket connectivity to {host}:{port}")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print(f"   ✅ Socket connection successful")
            return True
        else:
            print(f"   ❌ Socket connection failed (error code: {result})")
            return False
            
    except Exception as e:
        print(f"   ❌ Socket test failed: {e}")
        return False


def test_http_request(url, verbose=False):
    """Test HTTP request with detailed diagnostics"""
    print(f"\n🌐 Testing HTTP request to: {url}")
    
    try:
        # Create request with headers
        request = urllib.request.Request(url)
        request.add_header('User-Agent', 'Trepan-Debug-Bridge/1.0')
        request.add_header('Accept', 'application/json')
        
        print(f"   📤 Request headers:")
        for header, value in request.headers.items():
            print(f"      {header}: {value}")
        
        # Make the request
        start_time = time.time()
        with urllib.request.urlopen(request, timeout=10) as response:
            response_time = time.time() - start_time
            
            # Response info
            print(f"   📥 Response received in {response_time:.3f}s")
            print(f"   📊 Status: {response.getcode()} {response.reason}")
            
            # Response headers
            print(f"   📋 Response headers:")
            for header, value in response.headers.items():
                print(f"      {header}: {value}")
            
            # Response body
            body = response.read().decode('utf-8')
            print(f"   📄 Response body ({len(body)} bytes):")
            
            try:
                # Try to parse as JSON
                data = json.loads(body)
                print(f"      {json.dumps(data, indent=6)}")
                
                # Analyze Trepan-specific response
                if isinstance(data, dict):
                    if 'status' in data:
                        status = data['status']
                        print(f"   🛡️  Trepan Status: {status}")
                        
                        if status == 'ok':
                            print(f"      ✅ Server is healthy")
                        else:
                            print(f"      ⚠️  Server status not OK")
                    
                    if 'model_loaded' in data:
                        model_loaded = data['model_loaded']
                        print(f"   🤖 Model Loaded: {model_loaded}")
                        
                        if model_loaded:
                            print(f"      ✅ Model is ready for inference")
                        else:
                            print(f"      ⚠️  Model is still loading")
                
            except json.JSONDecodeError:
                print(f"      {body}")
                print(f"   ⚠️  Response is not valid JSON")
            
            return True
            
    except urllib.error.HTTPError as e:
        print(f"   ❌ HTTP Error {e.code}: {e.reason}")
        
        # Try to read error response
        try:
            error_body = e.read().decode('utf-8')
            print(f"   📄 Error response body:")
            print(f"      {error_body}")
        except:
            pass
            
        return False
        
    except urllib.error.URLError as e:
        print(f"   ❌ URL Error: {e.reason}")
        
        # Provide specific guidance based on error
        if 'Connection refused' in str(e.reason):
            print(f"   💡 This usually means:")
            print(f"      - Server is not running")
            print(f"      - Server is running on different port")
            print(f"      - Firewall is blocking the connection")
        elif 'timeout' in str(e.reason).lower():
            print(f"   💡 This usually means:")
            print(f"      - Server is overloaded or slow")
            print(f"      - Network connectivity issues")
            print(f"      - Server is starting up")
        
        return False
        
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False


def test_server_endpoints(base_url, verbose=False):
    """Test multiple server endpoints"""
    endpoints = [
        '/health',
        '/docs',
        '/',
    ]
    
    print(f"\n🎯 Testing server endpoints at {base_url}")
    results = {}
    
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        print(f"\n   Testing: {endpoint}")
        
        try:
            request = urllib.request.Request(url)
            with urllib.request.urlopen(request, timeout=5) as response:
                status = response.getcode()
                content_type = response.headers.get('content-type', 'unknown')
                content_length = response.headers.get('content-length', 'unknown')
                
                print(f"      ✅ {status} - {content_type} ({content_length} bytes)")
                results[endpoint] = {'status': status, 'success': True}
                
        except urllib.error.HTTPError as e:
            print(f"      ❌ HTTP {e.code}: {e.reason}")
            results[endpoint] = {'status': e.code, 'success': False}
        except Exception as e:
            print(f"      ❌ Error: {e}")
            results[endpoint] = {'error': str(e), 'success': False}
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Trepan WSL Bridge Diagnostic Tool")
    parser.add_argument("--host", default="localhost", help="Server host (default: localhost)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    args = parser.parse_args()
    
    print("=" * 80)
    print("🔍 TREPAN WSL BRIDGE DIAGNOSTICS")
    print("=" * 80)
    
    # System information
    print("\n📋 System Information:")
    sys_info = get_system_info()
    for key, value in sys_info.items():
        if key == 'ip_addresses':
            print(f"   {key}: {', '.join(value) if isinstance(value, list) else value}")
        else:
            print(f"   {key}: {value}")
    
    # Test different host variations
    hosts_to_test = [args.host]
    if args.host == "localhost":
        hosts_to_test.extend(["127.0.0.1", "0.0.0.0"])
    
    # Add system IP addresses if available
    if 'ip_addresses' in sys_info:
        for ip in sys_info['ip_addresses']:
            if ip not in hosts_to_test and ip != '127.0.0.1':
                hosts_to_test.append(ip)
    
    print(f"\n🎯 Testing hosts: {', '.join(hosts_to_test)}")
    
    successful_connections = []
    
    for host in hosts_to_test:
        print(f"\n" + "─" * 60)
        print(f"Testing: {host}:{args.port}")
        print("─" * 60)
        
        # Test socket connectivity
        socket_ok = test_port_connectivity(host, args.port)
        
        if socket_ok:
            # Test HTTP health endpoint
            health_url = f"http://{host}:{args.port}/health"
            http_ok = test_http_request(health_url, args.verbose)
            
            if http_ok:
                successful_connections.append(f"{host}:{args.port}")
                
                # Test additional endpoints
                base_url = f"http://{host}:{args.port}"
                endpoint_results = test_server_endpoints(base_url, args.verbose)
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 DIAGNOSTIC SUMMARY")
    print("=" * 80)
    
    if successful_connections:
        print(f"✅ Successful connections: {len(successful_connections)}")
        for conn in successful_connections:
            print(f"   - http://{conn}")
        
        print(f"\n💡 Recommendations:")
        print(f"   1. Use any of the successful URLs in your VS Code extension")
        print(f"   2. Update extension serverUrl setting to working URL")
        print(f"   3. Server is accessible and responding correctly")
        
        if sys_info.get('is_wsl'):
            print(f"\n🐧 WSL-specific notes:")
            print(f"   - Server is running in WSL2 environment")
            print(f"   - Windows VS Code can access via any successful URL above")
            print(f"   - If extension still shows offline, check VS Code extension logs")
    else:
        print(f"❌ No successful connections found")
        print(f"\n🔧 Troubleshooting steps:")
        print(f"   1. Check if Trepan server is running:")
        print(f"      python start_server.py --host 0.0.0.0 --port {args.port}")
        print(f"   2. Check if Ollama is running:")
        print(f"      ollama serve")
        print(f"   3. Check firewall settings")
        print(f"   4. Try different ports: 8001, 8080, 3000")
        
        if sys_info.get('is_wsl'):
            print(f"\n🐧 WSL-specific troubleshooting:")
            print(f"   1. Ensure server binds to 0.0.0.0, not 127.0.0.1")
            print(f"   2. Check Windows firewall for WSL2 rules")
            print(f"   3. Try restarting WSL: wsl --shutdown && wsl")
    
    print("\n" + "=" * 80)
    print(f"Diagnostic completed at {datetime.now().isoformat()}")
    print("=" * 80)


if __name__ == "__main__":
    main()