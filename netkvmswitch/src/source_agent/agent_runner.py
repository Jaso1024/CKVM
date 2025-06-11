import sys
import os
import time
import logging

# Configure logging to a file and console
log_file_path = os.path.join(os.path.dirname(__file__), 'agent.log')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler(log_file_path),
                        logging.StreamHandler() # Also keep console output
                    ])

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from .client import SourceAgentClient
from common.config import config

def main():
    """Starts the source agent."""
    agent = SourceAgentClient()
    
    try:
        agent.start()
        print("Source agent started successfully.")
            # Keep the main thread alive while the agent runs in background threads
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping source agent...")
    finally:
        agent.stop()
        print("Source agent stopped.")

if __name__ == "__main__":
    main()
