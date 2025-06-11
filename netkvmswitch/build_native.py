#!/usr/bin/env python3
"""Build script for the native C++ backend."""

import os
import sys
import subprocess
import platform
from pathlib import Path
import shutil

def find_ffmpeg_path():
    """Try to find FFmpeg installation path."""
    
    # Check environment variable first
    if 'FFMPEG_PATH' in os.environ:
        return os.environ['FFMPEG_PATH']
    
    if platform.system() == "Windows":
        # Common Windows paths
        common_paths = [
            r"C:\Users\jaboh\Downloads\ffmpeg-master-latest-win64-gpl-shared\ffmpeg-master-latest-win64-gpl-shared",
            r"C:\ffmpeg",
            r"C:\tools\ffmpeg",
            os.path.expanduser("~/ffmpeg"),
        ]
        
        for path in common_paths:
            if os.path.exists(os.path.join(path, "include", "libavcodec")):
                return path
                
    elif platform.system() == "Linux":
        # Check if pkg-config can find FFmpeg
        try:
            subprocess.check_output(['pkg-config', '--exists', 'libavcodec'])
            return "system"  # Use system packages
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
            
        # Common Linux paths
        common_paths = [
            "/usr/local",
            "/opt/ffmpeg",
            os.path.expanduser("~/ffmpeg"),
        ]
        
        for path in common_paths:
            if os.path.exists(os.path.join(path, "include", "libavcodec")):
                return path
    
    return None

def install_dependencies():
    """Install required Python dependencies."""
    print("Installing Python dependencies...")
    
    dependencies = [
        "pybind11[global]",
        "numpy",
        "setuptools",
        "wheel",
    ]
    
    for dep in dependencies:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
        except subprocess.CalledProcessError as e:
            print(f"Failed to install {dep}: {e}")
            return False
    
    return True

def build_extension():
    """Build the C++ extension."""
    print("Building C++ extension...")
    
    # Find FFmpeg
    ffmpeg_path = find_ffmpeg_path()
    if not ffmpeg_path:
        print("ERROR: FFmpeg not found!")
        print("Please:")
        print("1. Install FFmpeg")
        print("2. Set FFMPEG_PATH environment variable to point to FFmpeg directory")
        print("3. Or ensure FFmpeg libraries are in system PATH")
        return False
    
    print(f"Using FFmpeg at: {ffmpeg_path}")
    
    # Set environment variable for setup.py
    if ffmpeg_path != "system":
        os.environ['FFMPEG_PATH'] = ffmpeg_path
    
    # Build the extension
    try:
        cmd = [sys.executable, "setup.py", "build_ext", "--inplace"]
        
        # Add debug info in development
        if "--debug" in sys.argv:
            cmd.extend(["--debug", "--force"])
            os.environ['CPPFLAGS'] = os.environ.get('CPPFLAGS', '') + ' -DDEBUG'
        
        subprocess.check_call(cmd)
        print("✓ C++ extension built successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to build C++ extension: {e}")
        return False

def main():
    """Main build function."""
    print("NetKVMSwitch Native Backend Builder")
    print("=" * 40)
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Install dependencies
    if not install_dependencies():
        print("✗ Failed to install dependencies")
        return 1
    
    # Build extension
    if not build_extension():
        print("✗ Build failed")
        return 1
    
    print("\n✓ Build completed successfully!")
    print("\nTo test the native backend:")
    print("  python -c \"import kvmstream_native; print('Native backend available')\"")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 