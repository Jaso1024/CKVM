#!/usr/bin/env python3

import socket
import subprocess
import platform

print("=== DETAILED CONNECTION CHECK ===")
print(f"Your IP: {socket.gethostbyname(socket.gethostname())}")

# Check if any device is trying to connect to KVM ports
print("\n=== KVM PORT CHECK ===")
kvm_ports = [7001, 7002, 8501, 12345, 12346, 12347, 12348]
for port in kvm_ports:
    try:
        sock = socket.socket()
        sock.settimeout(0.1)
        result = sock.connect_ex(('127.0.0.1', port))
        if result == 0:
            print(f'✅ Port {port} is open!')
        sock.close()
    except: 
        pass

# Show network interfaces  
print('\n=== NETWORK INTERFACES ===')
try:
    if platform.system().lower() == "windows":
        result = subprocess.run(['ipconfig'], capture_output=True, text=True, timeout=5)
    else:
        result = subprocess.run(['ifconfig'], capture_output=True, text=True, timeout=5)
    
    lines = result.stdout.split('\n')
    for line in lines[:30]:  # First 30 lines
        if any(keyword in line.lower() for keyword in ['adapter', 'address', 'inet', 'usb', 'ethernet']):
            print(line.strip())
except Exception as e: 
    print(f"Could not get network info: {e}")

# Check for active connections
print('\n=== ACTIVE CONNECTIONS ===')
try:
    result = subprocess.run(['netstat', '-an'], capture_output=True, text=True, timeout=5)
    lines = result.stdout.split('\n')
    established_count = 0
    for line in lines:
        if 'ESTABLISHED' in line:
            established_count += 1
            if established_count <= 5:  # Show first 5
                print(line.strip())
    
    if established_count > 5:
        print(f"... and {established_count - 5} more connections")
    
    print(f"Total established connections: {established_count}")
        
except Exception as e:
    print(f"Could not get connection info: {e}")

print('\n=== USB DEVICE CHECK (Alternative) ===')
try:
    if platform.system().lower() == "windows":
        result = subprocess.run(['powershell', 'Get-PnpDevice -Class USB | Select-Object FriendlyName, Status'], capture_output=True, text=True, timeout=10)
        if result.stdout.strip():
            lines = result.stdout.split('\n')
            usb_count = 0
            for line in lines:
                if 'OK' in line and 'FriendlyName' not in line:
                    usb_count += 1
                    if usb_count <= 5:
                        print(line.strip())
            
            if usb_count > 5:
                print(f"... and {usb_count - 5} more USB devices")
            print(f"Total USB devices: {usb_count}")
        else:
            print("No USB devices found via PowerShell")
    else:
        print("USB check not implemented for this platform")
        
except Exception as e:
    print(f"USB check failed: {e}") 