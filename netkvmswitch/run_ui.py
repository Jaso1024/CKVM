#!/usr/bin/env python3
"""
NetKVMSwitch UI Runner

This script starts the FastAPI web UI and the Central Hub server.
"""

import sys
import os
import multiprocessing
import uvicorn
import time

from src.central_hub.hub_runner import run_hub_process

def main():
    # Add the 'src' directory to the Python path
    src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'src'))
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # Start the Central Hub server in a separate process
    hub_process = multiprocessing.Process(target=run_hub_process, daemon=True)
    hub_process.start()
    print("[UI RUNNER] Hub process started.")
    
    # Give the hub a moment to start up
    time.sleep(2)

    # Start the FastAPI web UI using uvicorn
    print("[UI RUNNER] Starting FastAPI web UI...")
    try:
        # Note: We need to specify the app as a string 'module:app_object'
        # and set the working directory to 'src' so it can find the modules.
        uvicorn.run("web_ui.main:app", host="0.0.0.0", port=8000, reload=True, app_dir=src_path)
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
