#!/usr/bin/env python3
"""
NetKVMSwitch UI Runner

This script starts the Streamlit web UI for the NetKVMSwitch application.
"""

import sys
import os
import streamlit.web.cli as stcli

# This script is now the single entry point for the application.

def main():
    # Add the 'src' directory to the Python path
    # This allows for absolute imports from the project root (e.g., from common import config)
    src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'src'))
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # The path to the Streamlit app script
    app_path = os.path.join(src_path, 'ui', 'app.py')
    
    # Use Streamlit's own command line interface to run the app
    # This is a more robust way to launch Streamlit programmatically
    sys.argv = ["streamlit", "run", app_path]
    
    stcli.main()

if __name__ == "__main__":
    main() 