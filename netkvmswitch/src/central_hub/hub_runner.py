import sys
import os

from .server import CentralHubServer

def run_hub_process(port, network_accessible=False):
    """
    The target function for the server process.
    Initializes and runs the server until it's stopped.
    """
    print(f"[HUB RUNNER] Process started for port {port}. Network accessible: {network_accessible}")
    server = None
    try:
        server = CentralHubServer(port=port, network_accessible=network_accessible)
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
    from src.common.config import config
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=config.server.port)
    parser.add_argument("--network-accessible", action="store_true")
    args = parser.parse_args()
    run_hub_process(args.port, args.network_accessible)
