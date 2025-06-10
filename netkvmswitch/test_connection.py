#!/usr/bin/env python3

import sys
import os
import time
import threading

print("Script starting...")

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

try:
    from central_hub.server import CentralHubServer
    from source_agent.client import SourceAgentClient
    print("Imports successful")
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

def test_client_registration():
    """Test if client registers properly with the server."""
    print("Starting server...")
    
    # Start server
    server = CentralHubServer(host="127.0.0.1", port=8080, video_port=8081)
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()
    
    # Give server time to start
    time.sleep(2)
    
    print("Starting client...")
    
    # Start client
    client = SourceAgentClient(
        server_host="127.0.0.1", 
        server_port=8080, 
        video_port=8081,
        client_name="Test Client"
    )
    
    client_thread = threading.Thread(target=client.start, daemon=True)
    client_thread.start()
    
    # Give client time to connect and send CLIENT_HELLO
    time.sleep(5)
    
    # Check if client is registered
    all_clients = server.state_manager.get_all_clients()
    print(f"Registered clients: {list(all_clients.keys())}")
    
    if all_clients:
        print("✅ SUCCESS: Client registered successfully!")
        for addr, info in all_clients.items():
            print(f"  Client {addr}: {info.get('name', 'Unknown')}")
    else:
        print("❌ FAILED: No clients registered")
    
    # Cleanup
    client.stop()
    server.stop()

if __name__ == "__main__":
    test_client_registration() 