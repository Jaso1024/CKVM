import os
import sys

# The path to your FFmpeg bin directory
# This was identified in previous logs.
ffmpeg_bin_path = r"C:\Users\jaboh\Downloads\ffmpeg-master-latest-win64-gpl-shared\ffmpeg-master-latest-win64-gpl-shared\bin"

print(f"--- C++ Backend Load Test ---")
print(f"Attempting to use FFmpeg path: {ffmpeg_bin_path}")

# 1. Verify the FFmpeg directory exists
if not os.path.isdir(ffmpeg_bin_path):
    print(f"\n❌ ERROR: FFmpeg directory not found at the specified path.")
    print("Please ensure the path is correct.")
    sys.exit(1)

# 2. Add the FFmpeg directory to the DLL search path (for Python 3.8+)
# This is the modern, recommended way to handle DLLs on Windows.
try:
    os.add_dll_directory(os.path.abspath(ffmpeg_bin_path))
    print("✅ Successfully added FFmpeg path to DLL search path.")
except AttributeError:
    print("⚠️ Warning: `os.add_dll_directory` not available. Falling back to modifying PATH.")
    os.environ['PATH'] = os.path.abspath(ffmpeg_bin_path) + os.pathsep + os.environ['PATH']
except Exception as e:
    print(f"\n❌ ERROR: Could not add DLL directory: {e}")
    sys.exit(1)

# 3. Attempt to import the native module
print("Attempting to import `kvmstream_native`...")
try:
    # We need to make sure the current directory is in the path to find the .pyd file
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import kvmstream_native
    print("\n🚀🚀🚀 Native backend is fully operational! 🚀🚀🚀")
    print("The `.pyd` module was found and all required FFmpeg DLLs were loaded successfully.")
except ImportError as e:
    print("\n❌❌❌ FATAL: Failed to import native backend. ❌❌❌")
    print("This error means that even after telling Python where to find the FFmpeg DLLs,")
    print("the import failed. This could be due to:")
    print("  1. An architecture mismatch (e.g., 32-bit Python trying to load 64-bit DLLs).")
    print("  2. A corrupted FFmpeg installation.")
    print("  3. A missing dependency of the FFmpeg DLLs themselves.")
    print("\n--- Detailed Python Error ---")
    print(e)
    print("-----------------------------\n")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ An unexpected error occurred: {e}")
    sys.exit(1) 