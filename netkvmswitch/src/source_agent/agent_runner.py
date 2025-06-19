import sys
import os
import time
import logging
import argparse

# Configure logging to a file and console
log_file_path = os.path.join(os.path.dirname(__file__), 'agent.log')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler(log_file_path),
                        logging.StreamHandler() # Also keep console output
                    ])

from .client import SourceAgentClient
from common.config import config

def main(port=None, network_accessible=False):
    """Starts the source agent."""
    agent = SourceAgentClient(server_port=port, network_accessible=network_accessible)
    
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
    # This allows the bundled exe to be re-invoked to run the agent
    if len(sys.argv) > 1 and sys.argv[1] == '--run-agent':
        port = int(sys.argv[2]) if len(sys.argv) > 2 else None
        network_accessible = '--network-accessible' in sys.argv
        main(port=port, network_accessible=network_accessible)
    # When running from the command line in development, we also want to run main
    elif not getattr(sys, 'frozen', False):
        parser = argparse.ArgumentParser()
        parser.add_argument("--port", type=int, default=config.client.server_port)
        parser.add_argument("--network-accessible", action="store_true")
        args = parser.parse_args()
        main(port=args.port, network_accessible=args.network_accessible)
