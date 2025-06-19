#!/usr/bin/env python3
"""
NetKVMSwitch UI Runner

This script starts the FastAPI web UI and the Central Hub server.
"""
import sys
import multiprocessing
import uvicorn
import time
import argparse

def main():
    from src.central_hub.hub_runner import run_hub_process
    from src.web_ui.main import app
    from src.common.config import config

    parser = argparse.ArgumentParser()
    parser.add_argument("--network-accessible", action="store_true", help="Allow network access to the hub")
    args = parser.parse_args()

    # Start the Central Hub server in a separate process
    hub_process = multiprocessing.Process(target=run_hub_process, args=(config.server.port, args.network_accessible), daemon=True)
    hub_process.start()
    print("[UI RUNNER] Hub process started.")
    
    # Give the hub a moment to start up
    time.sleep(2)

    # Start the FastAPI web UI using uvicorn
    print(f"[UI RUNNER] Starting FastAPI web UI on port {config.ui.port}...")
    try:
        uvicorn.run(app, host="0.0.0.0", port=config.ui.port, reload=False)
    finally:
        print("[UI RUNNER] Uvicorn server has shut down. Terminating hub process.")
        if hub_process.is_alive():
            hub_process.terminate()
            hub_process.join()
        print("[UI RUNNER] Hub process terminated.")

if __name__ == "__main__":
    # This is necessary for multiprocessing on Windows
    if sys.platform == 'win32':
        multiprocessing.freeze_support()
    main()
