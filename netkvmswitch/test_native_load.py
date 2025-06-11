# test_native_load.py
import sys

def run_test():
    """Test loading the statically-linked native module."""
    
    print("Attempting to import the native module 'kvmstream_native'...")
    
    try:
        import kvmstream_native
        print("\n" + "="*50)
        print("✅ SUCCESS: Statically-linked native backend loaded!")
        print("="*50 + "\n")

    except ImportError as e:
        print("\n" + "!"*50, file=sys.stderr)
        print("❌ FAILURE: Failed to import 'kvmstream_native'.", file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        print("!"*50 + "\n", file=sys.stderr)
        print("Troubleshooting: This usually means the build failed. Check the output of 'build_native.py'.", file=sys.stderr)
        sys.exit(1)
        
    print("Native module imported successfully. Verifying functionality...")
    try:
        config = kvmstream_native.StreamConfig()
        print(f"-> Default config: {config.width}x{config.height} @ {config.fps} FPS")
        
        capturer = kvmstream_native.ScreenCapturer()
        print("-> ScreenCapturer object created")
        
        encoder = kvmstream_native.H264Encoder()
        print("-> H264Encoder object created")
        
        print("\n🚀🚀🚀 Native backend is fully operational! 🚀🚀🚀")
    
    except Exception as e:
        print(f"❌ ERROR during functionality test: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    run_test() 