#!/usr/bin/env python3
"""
NetKVMSwitch UI Runner

This script starts the Streamlit web UI for the NetKVMSwitch application.
"""

import sys
import os
import subprocess

# This script is now the single entry point for the application.

def main():
    # Get the absolute path to the ui/app.py file
    # This ensures the path is correct regardless of where this script is run from.
    # The __file__ magic variable gives the path of the current script.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ui_app_path = os.path.join(script_dir, 'src', 'ui', 'app.py')

    cmd = [
        sys.executable, '-m', 'streamlit', 'run', ui_app_path,
        '--server.port', str(config.ui.port),
        '--server.address', config.ui.host
    ]
    
    print("==========================================")
    print("    Starting NetKVMSwitch UI    ")
    print("==========================================")
    print(f"Access the UI at: http://localhost:{config.ui.port}")
    print("Press Ctrl+C in this terminal to stop the application.")
    print("------------------------------------------")

    try:
        # We use subprocess.run which waits for the command to complete.
        # This is what we want, as this script's job is just to launch streamlit.
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running Streamlit: {e}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nShutting down UI...")
    except FileNotFoundError:
        print("Error: 'streamlit' command not found.", file=sys.stderr)
        print("Please ensure Streamlit is installed in your environment (`pip install streamlit`)", file=sys.stderr)

if __name__ == "__main__":
    # Add src to path to load config, BEFORE calling main
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))
    from common.config import config
    
    main() 