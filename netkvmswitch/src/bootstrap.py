import sys
import os
import multiprocessing

def setup_paths():
    """
    Sets up the Python path correctly for both development and bundled modes.
    """
    if getattr(sys, 'frozen', False):
        # If the application is run as a bundle, the PyInstaller bootloader
        # extends the sys module by a flag frozen=True and sets the app 
        # path into variable _MEIPASS'.
        application_path = sys._MEIPASS
        # Add the root of the bundle to the path.
        sys.path.insert(0, application_path)
    else:
        # In development, the path is two levels up from this bootstrap script.
        application_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        sys.path.insert(0, application_path)

def main():
    """
    The main entry point for the application.
    """
    setup_paths()
    
    # Now that paths are set, we can import and run the main UI script.
    from src.run_ui import main as run_ui_main
    run_ui_main()

if __name__ == '__main__':
    # This is necessary for multiprocessing on Windows
    if sys.platform == 'win32':
        multiprocessing.freeze_support()
    main()
