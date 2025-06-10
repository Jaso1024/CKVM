import sys
import os

# This is a workaround for the module loading issue when running in a subprocess
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from central_hub.server import CentralHubServer

def run_hub_process():
    """
    The target function for the server process.
    Initializes and runs the server until it's stopped.
    """
    print("[HUB RUNNER] Process started.")
    server = None
    try:
        server = CentralHubServer()
        server.start()
        # Keep the process alive
        while server.running:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("[HUB RUNNER] Process interrupted.")
    except Exception as e:
        print(f"[HUB RUNNER] An error occurred: {e}")
    finally:
        if server:
            print("[HUB RUNNER] Stopping server.")
            server.stop()
        print("[HUB RUNNER] Process terminated.")

if __name__ == '__main__':
    # This allows the script to be run directly for testing if needed
    run_hub_process() 