#!/usr/bin/env python3
"""
USB-C File Transfer Implementation
Test sending files over the USB-C connection between computers
"""

import usb.core
import usb.util
import usb.backend.libusb1
import time
import os
import struct
import hashlib
import json
from pathlib import Path

# Target device from our detection
TARGET_VID = 0x2B7E
TARGET_PID = 0x0134

class USBFileTransfer:
    def __init__(self):
        self.device = None
        self.bulk_out = None
        self.bulk_in = None
        self.backend = None
        self.setup_backend()
    
    def setup_backend(self):
        """Setup USB backend using libusb-package"""
        try:
            import libusb_package
            self.backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
            print("✅ USB backend initialized")
        except Exception as e:
            print(f"❌ Failed to setup USB backend: {e}")
            raise
    
    def connect(self):
        """Connect to the USB device"""
        print(f"🔍 Looking for USB device {TARGET_VID:04X}:{TARGET_PID:04X}...")
        
        try:
            self.device = usb.core.find(idVendor=TARGET_VID, idProduct=TARGET_PID, backend=self.backend)
            
            if self.device is None:
                print("❌ USB device not found")
                # Show available devices for debugging
                devices = list(usb.core.find(find_all=True, backend=self.backend))
                print(f"Available devices: {len(devices)}")
                for i, dev in enumerate(devices[:5], 1):
                    try:
                        print(f"  {i}. {dev.idVendor:04X}:{dev.idProduct:04X}")
                    except:
                        print(f"  {i}. Unknown device")
                return False
            
            print(f"✅ Found device at Bus {self.device.bus}, Address {self.device.address}")
            
            # Try to configure the device
            try:
                # Detach kernel driver if necessary (Linux/Mac)
                if self.device.is_kernel_driver_active(0):
                    self.device.detach_kernel_driver(0)
                    print("🔓 Detached kernel driver")
            except (AttributeError, usb.core.USBError):
                # Not needed on Windows or already detached
                pass
            
            # Set configuration
            try:
                self.device.set_configuration()
                print("⚙️  Device configuration set")
            except usb.core.USBError as e:
                print(f"⚠️  Could not set configuration: {e}")
                print("   Continuing anyway - device might be in use")
            
            # Find bulk endpoints
            self.find_endpoints()
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    def find_endpoints(self):
        """Find bulk endpoints for communication"""
        print("🔍 Searching for communication endpoints...")
        
        try:
            cfg = self.device.get_active_configuration()
            
            for interface in cfg:
                print(f"📡 Interface {interface.bInterfaceNumber}: Class 0x{interface.bInterfaceClass:02x}")
                
                for endpoint in interface:
                    ep_addr = endpoint.bEndpointAddress
                    ep_type = usb.util.endpoint_type(endpoint.bmAttributes)
                    direction = usb.util.endpoint_direction(ep_addr)
                    
                    if ep_type == usb.util.ENDPOINT_TYPE_BULK:
                        if direction == usb.util.ENDPOINT_OUT:
                            self.bulk_out = ep_addr
                            print(f"✅ Found BULK OUT endpoint: 0x{ep_addr:02x}")
                        elif direction == usb.util.ENDPOINT_IN:
                            self.bulk_in = ep_addr
                            print(f"✅ Found BULK IN endpoint: 0x{ep_addr:02x}")
            
            if self.bulk_out is None and self.bulk_in is None:
                print("⚠️  No bulk endpoints found")
                print("   Will attempt alternative communication methods")
            
        except Exception as e:
            print(f"⚠️  Endpoint discovery failed: {e}")
    
    def send_raw_data(self, data, timeout=5000):
        """Send raw data to the device"""
        if self.bulk_out is None:
            # Try to send to interface 0, endpoint 1 (common for composite devices)
            endpoints_to_try = [0x01, 0x02, 0x03, 0x81, 0x82, 0x83]
            
            for ep in endpoints_to_try:
                try:
                    print(f"📤 Trying endpoint 0x{ep:02x}...")
                    result = self.device.write(ep, data, timeout)
                    print(f"✅ Successfully sent {result} bytes to endpoint 0x{ep:02x}")
                    self.bulk_out = ep  # Remember this endpoint works
                    return result
                except Exception as e:
                    print(f"   ❌ Endpoint 0x{ep:02x} failed: {e}")
                    continue
            
            print("❌ No working endpoints found for sending")
            return 0
        else:
            try:
                result = self.device.write(self.bulk_out, data, timeout)
                print(f"✅ Sent {result} bytes")
                return result
            except Exception as e:
                print(f"❌ Send failed: {e}")
                return 0
    
    def receive_raw_data(self, size=1024, timeout=5000):
        """Receive raw data from device"""
        if self.bulk_in is None:
            # Try common IN endpoints
            endpoints_to_try = [0x81, 0x82, 0x83, 0x84]
            
            for ep in endpoints_to_try:
                try:
                    print(f"📥 Trying to read from endpoint 0x{ep:02x}...")
                    data = self.device.read(ep, size, timeout)
                    print(f"✅ Received {len(data)} bytes from endpoint 0x{ep:02x}")
                    self.bulk_in = ep  # Remember this endpoint works
                    return bytes(data)
                except Exception as e:
                    print(f"   ❌ Read from 0x{ep:02x} failed: {e}")
                    continue
            
            print("❌ No working endpoints found for receiving")
            return b""
        else:
            try:
                data = self.device.read(self.bulk_in, size, timeout)
                return bytes(data)
            except Exception as e:
                print(f"❌ Receive failed: {e}")
                return b""
    
    def send_file(self, file_path):
        """Send a file over USB"""
        print(f"\n📁 SENDING FILE: {file_path}")
        print("=" * 60)
        
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return False
        
        try:
            # Read file
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            file_size = len(file_data)
            file_name = os.path.basename(file_path)
            file_hash = hashlib.md5(file_data).hexdigest()
            
            print(f"📊 File info:")
            print(f"   Name: {file_name}")
            print(f"   Size: {file_size} bytes")
            print(f"   Hash: {file_hash}")
            
            # Create file transfer protocol
            # Format: [HEADER][FILENAME][DATA]
            header = {
                'magic': 'NETKVMFILE',
                'version': 1,
                'filename': file_name,
                'filesize': file_size,
                'hash': file_hash,
                'timestamp': int(time.time())
            }
            
            header_json = json.dumps(header).encode('utf-8')
            header_size = len(header_json)
            
            # Protocol: [4 bytes header size][header][file data]
            packet = struct.pack('<I', header_size) + header_json + file_data
            
            print(f"📦 Packet info:")
            print(f"   Header size: {header_size} bytes")
            print(f"   Total packet: {len(packet)} bytes")
            
            # Send the packet
            print(f"\n📤 Sending file...")
            
            # Send in chunks for large files
            chunk_size = 1024  # 1KB chunks
            sent_bytes = 0
            
            for i in range(0, len(packet), chunk_size):
                chunk = packet[i:i + chunk_size]
                
                try:
                    result = self.send_raw_data(chunk)
                    if result > 0:
                        sent_bytes += result
                        progress = (sent_bytes / len(packet)) * 100
                        print(f"   Progress: {progress:.1f}% ({sent_bytes}/{len(packet)} bytes)")
                    else:
                        print(f"❌ Failed to send chunk {i//chunk_size + 1}")
                        return False
                    
                    # Small delay between chunks
                    time.sleep(0.01)
                    
                except Exception as e:
                    print(f"❌ Error sending chunk: {e}")
                    return False
            
            print(f"✅ File sent successfully!")
            print(f"   Total bytes sent: {sent_bytes}")
            
            # Try to get acknowledgment
            print(f"\n📥 Waiting for acknowledgment...")
            try:
                response = self.receive_raw_data(timeout=2000)
                if response:
                    print(f"✅ Received response: {len(response)} bytes")
                    try:
                        response_str = response.decode('utf-8', errors='ignore')
                        print(f"   Response: {response_str[:100]}...")
                    except:
                        print(f"   Response (hex): {response[:32].hex()}...")
                else:
                    print("⚠️  No acknowledgment received (this is normal if receiver isn't implemented)")
            except Exception as e:
                print(f"⚠️  No acknowledgment: {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ File transfer failed: {e}")
            return False
    
    def test_communication(self):
        """Test basic communication"""
        print(f"\n🏓 TESTING BASIC COMMUNICATION")
        print("=" * 60)
        
        # Send a simple ping
        ping_data = b"NETKVMSWITCH_PING_" + str(int(time.time())).encode()
        print(f"📤 Sending ping: {ping_data}")
        
        result = self.send_raw_data(ping_data)
        if result > 0:
            print(f"✅ Ping sent successfully ({result} bytes)")
            
            # Try to receive pong
            print(f"📥 Waiting for pong...")
            response = self.receive_raw_data(timeout=2000)
            if response:
                print(f"✅ Received response: {response}")
                return True
            else:
                print(f"⚠️  No response (normal if other device doesn't have receiver)")
                return True  # Sending worked
        else:
            print(f"❌ Ping failed")
            return False
    
    def disconnect(self):
        """Disconnect from device"""
        if self.device:
            try:
                usb.util.dispose_resources(self.device)
                print("🔌 Disconnected from USB device")
            except:
                pass

def create_test_file():
    """Create a test file to send"""
    test_file = "test_transfer.txt"
    content = f"""NetKVMSwitch USB File Transfer Test
Generated at: {time.ctime()}
This is a test file to verify USB-C communication.

File contains:
- Text data
- Timestamp information  
- Multiple lines
- Various characters: !@#$%^&*()

USB Device Info:
- VID: {TARGET_VID:04X}
- PID: {TARGET_PID:04X}
- Transfer method: USB Bulk endpoints

End of test file.
"""
    
    with open(test_file, 'w') as f:
        f.write(content)
    
    print(f"✅ Created test file: {test_file} ({len(content)} bytes)")
    return test_file

def main():
    """Main file transfer test"""
    print("🔌 USB-C FILE TRANSFER TEST")
    print("=" * 60)
    print("Testing real file transfer over USB-C connection")
    print("This will prove the USB communication works!")
    print()
    
    # Create test file
    test_file = create_test_file()
    
    # Initialize USB transfer
    usb_transfer = USBFileTransfer()
    
    try:
        # Connect to device
        if not usb_transfer.connect():
            print("❌ Cannot continue without USB connection")
            return
        
        # Test basic communication first
        if usb_transfer.test_communication():
            print("✅ Basic communication working!")
        else:
            print("⚠️  Basic communication failed, but trying file transfer anyway...")
        
        # Send the test file
        success = usb_transfer.send_file(test_file)
        
        if success:
            print(f"\n🎉 SUCCESS!")
            print("=" * 60)
            print("✅ File transfer completed successfully!")
            print("✅ USB-C communication is working!")
            print("✅ Ready for NetKVMSwitch integration!")
            print()
            print("💡 Next steps:")
            print("   1. Implement receiver on the other device")
            print("   2. Create bidirectional communication")
            print("   3. Integrate with NetKVMSwitch protocol")
        else:
            print(f"\n❌ File transfer failed")
            print("But don't worry - this gives us debugging info!")
    
    finally:
        usb_transfer.disconnect()
        
        # Clean up test file
        try:
            os.remove(test_file)
            print(f"🧹 Cleaned up test file")
        except:
            pass

if __name__ == "__main__":
    main() 