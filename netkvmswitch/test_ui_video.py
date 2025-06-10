#!/usr/bin/env python3

import sys
import os
import time
import threading
import socket
import numpy as np
import cv2

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from central_hub.server import CentralHubServer
from source_agent.client import SourceAgentClient

def test_ui_video_chunking():
    """Test if UI receives chunked video properly."""
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
    
    # Give client time to connect
    time.sleep(3)
    
    # Check if client is registered and video is flowing
    all_clients = server.state_manager.get_all_clients()
    print(f"Registered clients: {list(all_clients.keys())}")
    
    if all_clients:
        print("✅ Client registered successfully!")
        
        # Test UI video reception
        ui_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ui_socket.bind(('127.0.0.1', 8083))  # UI video port
        ui_socket.settimeout(5.0)
        
        frame_assembly = {}
        frames_received = 0
        
        print("Listening for UI video frames for 10 seconds...")
        start_time = time.time()
        
        while time.time() - start_time < 10 and frames_received < 5:
            try:
                data, addr = ui_socket.recvfrom(65536)
                
                # Parse chunk metadata
                if len(data) < 8:
                    continue
                    
                frame_id = int.from_bytes(data[0:4], 'big')
                chunk_num = int.from_bytes(data[4:6], 'big') 
                total_chunks = int.from_bytes(data[6:8], 'big')
                chunk_data = data[8:]
                
                print(f"Received UI chunk {chunk_num}/{total_chunks} for frame {frame_id} ({len(chunk_data)} bytes)")
                
                # Initialize frame assembly
                if frame_id not in frame_assembly:
                    frame_assembly[frame_id] = {"chunks": {}, "total_chunks": total_chunks}
                
                # Store chunk
                frame_assembly[frame_id]["chunks"][chunk_num] = chunk_data
                
                # Check if frame is complete
                frame_info = frame_assembly[frame_id]
                if len(frame_info["chunks"]) == frame_info["total_chunks"]:
                    # Assemble frame
                    complete_frame_data = bytearray()
                    for i in range(1, frame_info["total_chunks"] + 1):
                        if i in frame_info["chunks"]:
                            complete_frame_data.extend(frame_info["chunks"][i])
                        else:
                            break
                    else:
                        # Decode frame
                        try:
                            frame = cv2.imdecode(np.frombuffer(complete_frame_data, np.uint8), cv2.IMREAD_COLOR)
                            if frame is not None:
                                frames_received += 1
                                print(f"✅ Successfully decoded UI frame {frame_id}! Shape: {frame.shape}")
                            else:
                                print(f"❌ Failed to decode UI frame {frame_id}")
                        except Exception as e:
                            print(f"❌ Exception decoding UI frame {frame_id}: {e}")
                    
                    # Clean up
                    del frame_assembly[frame_id]
                    
            except socket.timeout:
                print("No UI video data received (timeout)")
                break
            except Exception as e:
                print(f"Error receiving UI video: {e}")
                break
        
        ui_socket.close()
        
        if frames_received > 0:
            print(f"✅ SUCCESS: Received and decoded {frames_received} complete frames in UI!")
        else:
            print("❌ FAILED: No complete frames received in UI")
    else:
        print("❌ FAILED: No clients registered")
    
    # Cleanup
    client.stop()
    server.stop()

if __name__ == "__main__":
    test_ui_video_chunking() 