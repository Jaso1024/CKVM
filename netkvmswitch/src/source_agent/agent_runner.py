import sys
import os
import time
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from source_agent.client import SourceAgentClient
from source_agent.usb_client import USBSourceAgent
from common.config import config

def run_agent_process(connection_type='network', settings=None):
    """
    The target function for the agent process.
    Initializes and runs the correct agent (Network or USB).
    """
    if len(sys.argv) > 1:
        connection_type = sys.argv[1]
    
    logging.info(f"[AGENT RUNNER] Process started for {connection_type} agent.")

    agent = None
    if connection_type.lower() == 'network':
        # Handle both dict and config object
        if isinstance(settings, dict):
            server_host = settings.get('server_host', config.client.server_host)
        else:
            server_host = settings.client.server_host if settings else config.client.server_host
        agent = SourceAgentClient(server_host=server_host)
    elif connection_type.lower() == 'usb':
        agent = USBSourceAgent()
    else:
        logging.error(f"[AGENT RUNNER] Invalid connection type: {connection_type}")
        sys.exit(1)

    try:
        agent.start()
        while agent.running:
            time.sleep(1)

    except KeyboardInterrupt:
        logging.info(f"[AGENT RUNNER] Process interrupted.")
    except Exception as e:
        logging.error(f"[AGENT RUNNER] An error occurred: {e}")
    finally:
        if agent:
            logging.info(f"[AGENT RUNNER] Stopping agent.")
            agent.stop()
        logging.info(f"[AGENT RUNNER] Process terminated.")

if __name__ == '__main__':
    # Example for direct testing
    run_agent_process(connection_type='network') 