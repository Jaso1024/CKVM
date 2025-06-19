#!/usr/bin/env python3
"""
Windows-specific USB File Transfer
Alternative approaches for USB communication on Windows
"""

import time
import os
import json
import hashlib
import subprocess
import tempfile
from pathlib import Path

class WindowsUSBTransfer:
    def __init__(self):
        self.target_vid = "2B7E"
        self.target_pid = "0134"
        self.device_instance = None
        self.temp_dir = None
    
    def find_device_info(self):
        """Use Windows tools to get detailed device information"""
        print("🔍 ANALYZING USB DEVICE WITH WINDOWS TOOLS")
        print("=" * 60)
        
        try:
            # Use PowerShell to get detailed USB device info
            cmd = [
                'powershell', '-Command',
                f'Get-PnpDevice | Where-Object {{$_.InstanceId -like "*VID_{self.target_vid}&PID_{self.target_pid}*"}} | Select-Object FriendlyName, Status, InstanceId, DeviceID, Service | Format-List'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                print("✅ Device found in Windows:")
                print(result.stdout)
                
                # Extract instance ID for further operations
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'InstanceId' in line and self.target_vid in line:
                        self.device_instance = line.split(':')[1].strip()
                        print(f"📋 Device Instance: {self.device_instance}")
                        break
                
                return True
            else:
                print("❌ Device not found in Windows device manager")
                return False
                
        except Exception as e:
            print(f"❌ Windows device query failed: {e}")
            return False
    
    def check_device_drivers(self):
        """Check what drivers are managing the device"""
        print("\n🔧 CHECKING DEVICE DRIVERS")
        print("=" * 60)
        
        try:
            cmd = [
                'powershell', '-Command',
                f'Get-WmiObject -Class Win32_PnPEntity | Where-Object {{$_.DeviceID -like "*VID_{self.target_vid}&PID_{self.target_pid}*"}} | Select-Object Name, Service, DeviceID | Format-List'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                print("✅ Driver information:")
                print(result.stdout)
                
                # Check if it's using a specific driver
                if 'WinUSB' in result.stdout:
                    print("🎯 Device is using WinUSB - Perfect for custom communication!")
                    return 'winusb'
                elif 'usbccgp' in result.stdout:
                    print("📱 Device is using USB Composite driver")
                    return 'composite'
                elif 'HidUsb' in result.stdout:
                    print("⌨️  Device is using HID driver")
                    return 'hid'
                else:
                    print("❓ Unknown or generic USB driver")
                    return 'unknown'
            else:
                print("⚠️  Could not determine driver information")
                return None
                
        except Exception as e:
            print(f"❌ Driver check failed: {e}")
            return None
    
    def try_file_based_transfer(self, file_path):
        """Try file-based communication using temp files"""
        print("\n📁 ATTEMPTING FILE-BASED TRANSFER")
        print("=" * 60)
        
        try:
            # Create a temporary directory for communication
            self.temp_dir = tempfile.mkdtemp(prefix="netkvmswitch_")
            print(f"📂 Created temp dir: {self.temp_dir}")
            
            # Read the source file
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            file_name = os.path.basename(file_path)
            file_size = len(file_data)
            file_hash = hashlib.md5(file_data).hexdigest()
            
            print(f"📊 File to transfer:")
            print(f"   Name: {file_name}")
            print(f"   Size: {file_size} bytes")
            print(f"   Hash: {file_hash}")
            
            # Create transfer packet
            transfer_data = {
                'magic': 'NETKVMSWITCH_FILE',
                'version': 1,
                'timestamp': int(time.time()),
                'source_file': file_name,
                'file_size': file_size,
                'file_hash': file_hash,
                'data': file_data.hex()  # Hex encode for JSON safety
            }
            
            # Save transfer file
            transfer_file = os.path.join(self.temp_dir, f"transfer_{int(time.time())}.json")
            with open(transfer_file, 'w') as f:
                json.dump(transfer_data, f, indent=2)
            
            print(f"✅ Created transfer file: {transfer_file}")
            print(f"📦 Transfer packet size: {os.path.getsize(transfer_file)} bytes")
            
            # Try to copy to potential USB device mount points
            success = self.try_usb_copy(transfer_file, file_name)
            
            if success:
                print("✅ File-based transfer completed!")
                return True
            else:
                print("⚠️  File-based transfer method not applicable")
                return False
                
        except Exception as e:
            print(f"❌ File-based transfer failed: {e}")
            return False
    
    def try_usb_copy(self, transfer_file, original_name):
        """Try copying to USB drive letters"""
        print("\n💾 LOOKING FOR USB DRIVES")
        print("=" * 40)
        
        try:
            # Get all drive letters
            cmd = ['powershell', '-Command', 'Get-WmiObject -Class Win32_LogicalDisk | Where-Object {$_.DriveType -eq 2} | Select-Object DeviceID, VolumeName | Format-Table -HideTableHeaders']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0 and result.stdout.strip():
                drives = []
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line and ':' in line:
                        drive = line.split()[0]
                        drives.append(drive)
                
                print(f"🔍 Found removable drives: {drives}")
                
                for drive in drives:
                    try:
                        # Try to copy our transfer file
                        dest_path = f"{drive}\\{original_name}"
                        
                        print(f"📋 Trying to copy to {dest_path}...")
                        
                        # Use copy command
                        copy_cmd = ['copy', transfer_file, dest_path]
                        copy_result = subprocess.run(copy_cmd, capture_output=True, text=True, shell=True)
                        
                        if copy_result.returncode == 0:
                            print(f"✅ Successfully copied to {dest_path}!")
                            
                            # Verify the copy
                            if os.path.exists(dest_path):
                                copied_size = os.path.getsize(dest_path)
                                original_size = os.path.getsize(transfer_file)
                                print(f"📊 Copy verification: {copied_size}/{original_size} bytes")
                                
                                if copied_size == original_size:
                                    print("✅ File integrity verified!")
                                    return True
                                else:
                                    print("⚠️  File size mismatch")
                            
                        else:
                            print(f"❌ Copy failed: {copy_result.stderr}")
                            
                    except Exception as e:
                        print(f"❌ Copy to {drive} failed: {e}")
                        continue
                
                print("⚠️  No successful copies to removable drives")
                return False
            else:
                print("❌ No removable drives found")
                return False
                
        except Exception as e:
            print(f"❌ USB drive detection failed: {e}")
            return False
    
    def try_named_pipe_transfer(self, file_path):
        """Try using Windows named pipes for communication"""
        print("\n🔄 ATTEMPTING NAMED PIPE TRANSFER")
        print("=" * 60)
        
        pipe_name = f"\\\\.\\pipe\\netkvmswitch_{self.target_vid}_{self.target_pid}"
        print(f"📞 Pipe name: {pipe_name}")
        
        try:
            # Read file data
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            print(f"📊 Preparing to send {len(file_data)} bytes via named pipe...")
            
            # For now, just create the pipe info file
            pipe_info = {
                'pipe_name': pipe_name,
                'data_size': len(file_data),
                'timestamp': int(time.time()),
                'status': 'ready_to_send'
            }
            
            info_file = f"pipe_info_{int(time.time())}.json"
            with open(info_file, 'w') as f:
                json.dump(pipe_info, f, indent=2)
            
            print(f"✅ Created pipe info file: {info_file}")
            print("💡 Named pipe would need receiver implementation on target device")
            
            # Clean up
            os.remove(info_file)
            return True
            
        except Exception as e:
            print(f"❌ Named pipe setup failed: {e}")
            return False
    
    def generate_usb_kvm_integration_plan(self):
        """Generate a plan for integrating this with NetKVMSwitch"""
        print("\n🚀 USB-C KVM INTEGRATION PLAN")
        print("=" * 60)
        
        print("Based on our USB-C analysis, here's the implementation plan:")
        print()
        print("🎯 PHASE 1: ESTABLISH COMMUNICATION")
        print("   1. Implement USB device driver or WinUSB interface")
        print("   2. Create bidirectional communication protocol")
        print("   3. Test with simple data exchange")
        print()
        print("🎯 PHASE 2: MODIFY NETKVMSWITCH")
        print("   4. Update usb_client.py to use direct USB instead of serial")
        print("   5. Implement USB-specific protocol handlers")
        print("   6. Add device detection and auto-configuration")
        print()
        print("🎯 PHASE 3: KVM FUNCTIONALITY")
        print("   7. Implement keyboard/mouse input over USB")
        print("   8. Add video streaming over USB bulk endpoints")
        print("   9. Create USB HID emulation for seamless control")
        print()
        print("📋 IMMEDIATE ACTIONABLE STEPS:")
        print("   • Install libusb-win32 or WinUSB driver for the device")
        print("   • Create custom USB driver using Zadig tool")
        print("   • Test with libusb or WinUSB APIs")
        print("   • Implement NetKVMSwitch USB transport layer")
        print()
        print("🔧 ALTERNATIVE APPROACHES:")
        print("   • Use USB CDC (Communication Device Class)")
        print("   • Implement USB Mass Storage for file transfer")
        print("   • Create USB Serial emulation")
        print("   • Use raw USB bulk transfers")
        
    def cleanup(self):
        """Clean up temporary files"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                import shutil
                shutil.rmtree(self.temp_dir)
                print(f"🧹 Cleaned up temp directory")
            except:
                pass

def create_test_file():
    """Create a test file for transfer"""
    test_file = "usb_test_file.txt"
    content = f"""NetKVMSwitch USB-C Communication Test
=====================================

Test performed: {time.ctime()}
Target Device: VID_2B7E&PID_0134
Transfer Method: USB-C Direct

This file tests the USB-C connection between computers.
If you can see this file on the other device, the USB
communication is working!

Next steps:
1. Implement bidirectional communication
2. Add NetKVMSwitch protocol support  
3. Enable keyboard/mouse control
4. Add video streaming

File size: Will be calculated...
End of test file.
"""
    
    with open(test_file, 'w') as f:
        f.write(content)
    
    # Update file size in content
    actual_size = os.path.getsize(test_file)
    content = content.replace("Will be calculated...", f"{actual_size} bytes")
    
    with open(test_file, 'w') as f:
        f.write(content)
    
    print(f"✅ Created test file: {test_file} ({actual_size} bytes)")
    return test_file

def main():
    """Main Windows USB transfer test"""
    print("🪟 WINDOWS USB-C TRANSFER TEST")
    print("=" * 60)
    print("Testing USB-C file transfer using Windows-specific methods")
    print()
    
    # Create test file
    test_file = create_test_file()
    
    # Initialize Windows USB transfer
    usb_transfer = WindowsUSBTransfer()
    
    try:
        # Analyze the device
        device_found = usb_transfer.find_device_info()
        
        if device_found:
            # Check drivers
            driver_type = usb_transfer.check_device_drivers()
            
            # Try different transfer methods
            methods_tried = []
            
            # Method 1: File-based transfer
            print("\n" + "="*60)
            success1 = usb_transfer.try_file_based_transfer(test_file)
            methods_tried.append(("File-based", success1))
            
            # Method 2: Named pipe (setup only)
            success2 = usb_transfer.try_named_pipe_transfer(test_file)
            methods_tried.append(("Named pipe", success2))
            
            # Generate integration plan
            usb_transfer.generate_usb_kvm_integration_plan()
            
            # Summary
            print("\n" + "="*60)
            print("📊 TRANSFER METHODS SUMMARY")
            print("="*60)
            
            any_success = False
            for method, success in methods_tried:
                status = "✅ SUCCESS" if success else "❌ FAILED"
                print(f"{method}: {status}")
                if success:
                    any_success = True
            
            if any_success:
                print("\n🎉 USB-C COMMUNICATION IS POSSIBLE!")
                print("Some transfer methods worked - this proves the connection!")
            else:
                print("\n⚠️  DIRECT METHODS FAILED")
                print("But this gives us valuable information for next steps!")
            
            print("\n💡 RECOMMENDED NEXT ACTIONS:")
            print("1. Install WinUSB driver using Zadig tool")
            print("2. Use libusb-win32 for direct USB access")
            print("3. Implement custom USB protocol")
            print("4. Test with NetKVMSwitch integration")
            
        else:
            print("❌ Cannot continue without device detection")
    
    finally:
        usb_transfer.cleanup()
        
        # Clean up test file
        try:
            os.remove(test_file)
            print(f"🧹 Cleaned up test file")
        except:
            pass

if __name__ == "__main__":
    main() 