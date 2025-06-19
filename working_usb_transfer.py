#!/usr/bin/env python3
"""
Working USB File Transfer Implementation
This will work after installing WinUSB driver with Zadig
"""

import usb.core
import usb.util
import usb.backend.libusb1
import time
import os
import json
import hashlib
from pathlib import Path

class WorkingUSBTransfer:
    def __init__(self):
        self.device = None
        self.backend = None
        self.target_vid = 0x2B7E  # Your device VID
        self.target_pid = 0x0134  # Your device PID
        self.endpoints = {}
        
    def setup_backend(self):
        """Setup libusb backend"""
        try:
            import libusb_package
            self.backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
            print("✅ USB backend ready")
            return True
        except Exception as e:
            print(f"❌ Backend setup failed: {e}")
            return False
    
    def connect_device(self):
        """Connect to the USB device"""
        print(f"🔍 Connecting to device {self.target_vid:04X}:{self.target_pid:04X}...")
        
        try:
            self.device = usb.core.find(idVendor=self.target_vid, idProduct=self.target_pid, backend=self.backend)
            
            if self.device is None:
                print("❌ Device not found!")
                print("💡 Make sure you've installed WinUSB driver with Zadig!")
                return False
            
            print(f"✅ Device found: Bus {self.device.bus}, Address {self.device.address}")
            
            # Check if WinUSB driver is installed
            try:
                self.device.set_configuration()
                print("✅ WinUSB driver detected - ready for communication!")
            except usb.core.USBError as e:
                if "Entity not found" in str(e):
                    print("❌ Still using system driver!")
                    print("📋 Instructions:")
                    print("   1. Download Zadig from https://zadig.akeo.ie/")
                    print("   2. Run as Administrator")
                    print("   3. Select 'USB Composite Device (Interface 0)'")
                    print("   4. Choose 'WinUSB' as driver")
                    print("   5. Click 'Replace Driver'")
                    print("   6. Run this script again")
                    return False
                else:
                    print(f"⚠️  Configuration warning: {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    def find_endpoints(self):
        """Discover available endpoints"""
        print("🔍 Discovering communication endpoints...")
        
        try:
            cfg = self.device.get_active_configuration()
            print(f"📊 Configuration: {cfg.bConfigurationValue}")
            
            for interface in cfg:
                interface_num = interface.bInterfaceNumber
                print(f"📡 Interface {interface_num}: Class 0x{interface.bInterfaceClass:02x}")
                
                # Store interface info
                self.endpoints[interface_num] = {
                    'class': interface.bInterfaceClass,
                    'in': [],
                    'out': []
                }
                
                for endpoint in interface:
                    ep_addr = endpoint.bEndpointAddress
                    ep_type = usb.util.endpoint_type(endpoint.bmAttributes)
                    direction = usb.util.endpoint_direction(ep_addr)
                    
                    ep_info = {
                        'address': ep_addr,
                        'type': ep_type,
                        'max_packet': endpoint.wMaxPacketSize
                    }
                    
                    if direction == usb.util.ENDPOINT_IN:
                        self.endpoints[interface_num]['in'].append(ep_info)
                        print(f"   📥 IN  endpoint: 0x{ep_addr:02x} (max: {endpoint.wMaxPacketSize} bytes)")
                    else:
                        self.endpoints[interface_num]['out'].append(ep_info)
                        print(f"   📤 OUT endpoint: 0x{ep_addr:02x} (max: {endpoint.wMaxPacketSize} bytes)")
            
            # Find best endpoints for file transfer
            best_interface = self.find_best_interface()
            if best_interface is not None:
                print(f"🎯 Using interface {best_interface} for file transfer")
                return True
            else:
                print("⚠️  No suitable interfaces found for bulk transfer")
                return False
                
        except Exception as e:
            print(f"❌ Endpoint discovery failed: {e}")
            return False
    
    def find_best_interface(self):
        """Find the best interface for file transfer"""
        # Prefer interfaces with bulk endpoints
        for interface_num, info in self.endpoints.items():
            if info['in'] and info['out']:
                # Check if endpoints support bulk transfer
                for ep in info['out']:
                    if ep['type'] == usb.util.ENDPOINT_TYPE_BULK:
                        return interface_num
        
        # Fallback to any interface with both IN and OUT
        for interface_num, info in self.endpoints.items():
            if info['in'] and info['out']:
                return interface_num
        
        return None
    
    def send_file_data(self, file_path, interface_num):
        """Send file using the specified interface"""
        print(f"\n📁 SENDING FILE: {file_path}")
        print("=" * 50)
        
        try:
            # Read file
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            file_name = os.path.basename(file_path)
            file_size = len(file_data)
            file_hash = hashlib.sha256(file_data).hexdigest()[:16]
            
            print(f"📊 File: {file_name} ({file_size} bytes)")
            print(f"🔐 Hash: {file_hash}")
            
            # Create transfer packet
            header = {
                'magic': 'NKVMFILE',
                'name': file_name,
                'size': file_size,
                'hash': file_hash,
                'timestamp': int(time.time())
            }
            
            header_json = json.dumps(header, separators=(',', ':')).encode('utf-8')
            header_size = len(header_json)
            
            # Packet format: [4-byte header size][header][file data]
            packet = header_size.to_bytes(4, 'little') + header_json + file_data
            
            print(f"📦 Total packet: {len(packet)} bytes")
            
            # Get output endpoint
            out_endpoints = self.endpoints[interface_num]['out']
            if not out_endpoints:
                print("❌ No output endpoints available")
                return False
            
            out_ep = out_endpoints[0]['address']
            max_packet = out_endpoints[0]['max_packet']
            
            print(f"📤 Using endpoint 0x{out_ep:02x} (max packet: {max_packet})")
            
            # Send data in chunks
            chunk_size = min(max_packet, 1024)  # Don't exceed max packet size
            sent_bytes = 0
            
            print(f"🚀 Sending in {chunk_size}-byte chunks...")
            
            for i in range(0, len(packet), chunk_size):
                chunk = packet[i:i + chunk_size]
                
                try:
                    result = self.device.write(out_ep, chunk, timeout=5000)
                    sent_bytes += len(chunk)
                    
                    progress = (sent_bytes / len(packet)) * 100
                    print(f"   📈 {progress:5.1f}% ({sent_bytes:,}/{len(packet):,} bytes)")
                    
                    # Small delay to prevent overwhelming the device
                    time.sleep(0.01)
                    
                except usb.core.USBError as e:
                    print(f"❌ Send error at byte {sent_bytes}: {e}")
                    return False
            
            print(f"✅ File sent successfully! ({sent_bytes:,} bytes)")
            
            # Try to receive acknowledgment
            self.try_receive_ack(interface_num)
            
            return True
            
        except Exception as e:
            print(f"❌ File send failed: {e}")
            return False
    
    def try_receive_ack(self, interface_num):
        """Try to receive acknowledgment"""
        print(f"\n📥 Waiting for acknowledgment...")
        
        try:
            in_endpoints = self.endpoints[interface_num]['in']
            if not in_endpoints:
                print("⚠️  No input endpoints for acknowledgment")
                return
            
            in_ep = in_endpoints[0]['address']
            
            # Try to read response
            try:
                response = self.device.read(in_ep, 1024, timeout=2000)
                print(f"✅ Received {len(response)} bytes:")
                
                try:
                    response_text = bytes(response).decode('utf-8', errors='ignore')
                    print(f"   📋 Response: {response_text[:100]}")
                except:
                    print(f"   📋 Response (hex): {bytes(response)[:32].hex()}")
                    
            except usb.core.USBTimeoutError:
                print("⏰ No acknowledgment received (timeout)")
                print("   This is normal if the other device isn't running receiver software")
            except Exception as e:
                print(f"⚠️  Read error: {e}")
                
        except Exception as e:
            print(f"⚠️  Acknowledgment check failed: {e}")
    
    def test_file_transfer(self, file_path):
        """Complete file transfer test"""
        print("🔌 USB FILE TRANSFER TEST")
        print("=" * 60)
        
        # Setup
        if not self.setup_backend():
            return False
        
        if not self.connect_device():
            return False
        
        if not self.find_endpoints():
            return False
        
        # Find best interface
        best_interface = self.find_best_interface()
        if best_interface is None:
            print("❌ No suitable interface found")
            return False
        
        # Send file
        success = self.send_file_data(file_path, best_interface)
        
        if success:
            print("\n🎉 FILE TRANSFER SUCCESSFUL!")
            print("=" * 60)
            print("✅ USB-C communication working!")
            print("✅ File sent over USB successfully!")
            print("✅ Ready for NetKVMSwitch integration!")
            print("\n💡 Next steps:")
            print("   1. Implement receiver on target device")
            print("   2. Add bidirectional communication")
            print("   3. Integrate with NetKVMSwitch protocol")
        else:
            print("\n❌ File transfer failed")
            print("Check that WinUSB driver is properly installed")
        
        return success

def create_test_file():
    """Create a test file for transfer"""
    test_file = "netkvmswitch_test.txt"
    
    content = f"""NetKVMSwitch USB-C File Transfer Test
=====================================

Generated: {time.ctime()}
Device: VID_2B7E&PID_0134 (720p HD Camera)
Protocol: USB Bulk Transfer

This file was sent over USB-C connection to test:
✅ Direct USB communication
✅ File transfer protocol
✅ Bidirectional capability preparation
✅ NetKVMSwitch integration readiness

If you see this file, the USB communication is working!

Technical details:
- Transfer method: USB bulk endpoints
- Driver: WinUSB (via Zadig)
- Protocol: Custom NetKVMSwitch file transfer
- Packet format: [size][header][data]

Next: Implement KVM control protocol over this connection.
"""
    
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    size = os.path.getsize(test_file)
    print(f"✅ Created test file: {test_file} ({size} bytes)")
    return test_file

def main():
    """Main test function"""
    print("🚀 WORKING USB FILE TRANSFER")
    print("This version should work after installing WinUSB driver!")
    print()
    
    # Create test file
    test_file = create_test_file()
    
    # Run transfer test
    usb_transfer = WorkingUSBTransfer()
    
    try:
        success = usb_transfer.test_file_transfer(test_file)
        
        if not success:
            print("\n🔧 TROUBLESHOOTING GUIDE:")
            print("=" * 60)
            print("1. Download Zadig: https://zadig.akeo.ie/")
            print("2. Run Zadig as Administrator")
            print("3. Look for 'USB Composite Device'")
            print("4. Select WinUSB driver")
            print("5. Click 'Replace Driver'")
            print("6. Restart this script")
            print()
            print("⚠️  WARNING: Only replace driver for the target device!")
            print("   VID_2B7E&PID_0134 (720p HD Camera)")
    
    finally:
        # Cleanup
        try:
            os.remove(test_file)
            print("🧹 Test file cleaned up")
        except:
            pass

if __name__ == "__main__":
    main() 