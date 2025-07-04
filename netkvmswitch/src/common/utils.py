# Shared utilities
import os
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = os.path.join(sys._MEIPASS, 'src')
    except Exception:
        # In development, the base path is the root of the project
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    return os.path.join(base_path, relative_path)
