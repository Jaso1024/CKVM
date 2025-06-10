# Main server logic, network, K/M capture

import socket
import threading
import json
import cv2
import numpy as np
from pynput import keyboard, mouse
import time
import ssl
import sys
import os
import serial
import serial.tools.list_ports
import base64

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.protocol import create_message, parse_message, MessageType
from common.serial_protocol import send_framed, receive_framed
from common.config import config
from central_hub.state_manager import StateManager

class CentralHubServer:
    def __init__(self, host=None, port=None, video_port=None):
        self.host = host or config.server.host
        self.port = port or config.server.port
        self.video_port = video_port or config.server.video_port
        self.ui_control_port = config.server.ui_control_port
        self.ui_video_port = config.server.ui_video_port
        self.server_socket = None
        self.video_socket = None
        self.ui_control_socket = None
        self.running = False

        self.state_manager = StateManager()

        self.keyboard_listener = None
        self.mouse_listener = None

    def start(self):
        import os

        certs_dir = config.get_certs_dir()

        if config.security.use_tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(
                os.path.join(certs_dir, config.security.server_cert), 
                os.path.join(certs_dir, config.security.server_key)
            )
            context.load_verify_locations(os.path.join(certs_dir, config.security.ca_cert))
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = False

        # Main client connection socket (TLS)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        if config.security.use_tls:
            self.server_socket = context.wrap_socket(self.server_socket, server_side=True)

        # Video streaming socket (UDP)
        self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.video_socket.bind((self.host, self.video_port))

        # UI control socket (TCP, no TLS for local communication)
        self.ui_control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ui_control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ui_control_socket.bind((self.host, self.ui_control_port))
        self.ui_control_socket.listen(5)

        self.running = True
        print(f"Server listening on:")
        print(f"  Client connections: {self.host}:{self.port} (TCP{'S' if config.security.use_tls else ''})")
        print(f"  Video streams: {self.host}:{self.video_port} (UDP)")
        print(f"  UI control: {self.host}:{self.ui_control_port} (TCP)")

        threading.Thread(target=self._accept_connections, daemon=True).start()
        threading.Thread(target=self._accept_ui_connections, daemon=True).start()
        threading.Thread(target=self._receive_video_streams, daemon=True).start()
        threading.Thread(target=self._listen_for_usb_agents, daemon=True).start()
        self._start_input_listeners()

    def _accept_connections(self):
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                # The accepted 'conn' is already an SSLSocket due to wrap_socket on the listening socket
                print(f"Accepted connection from {addr}")
                # Client will be added to state_manager upon receiving CLIENT_HELLO
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
                self._send_server_ack(conn)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error accepting connections: {e}")
                break

    def _accept_ui_connections(self):
        """Accept connections from the UI for control commands."""
        while self.running:
            try:
                conn, addr = self.ui_control_socket.accept()
                print(f"UI connected from {addr}")
                threading.Thread(target=self._handle_ui_client, args=(conn, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error accepting UI connections: {e}")
                break

    def _handle_ui_client(self, conn, addr):
        """Handle commands from the UI."""
        while self.running:
            try:
                data = conn.recv(4096)
                if not data:
                    print(f"UI {addr} disconnected.")
                    break
                
                message = parse_message(data)
                response = self._process_ui_command(message)
                
                if response:
                    conn.sendall(create_message("response", response))
                    
            except ConnectionResetError:
                print(f"UI {addr} forcibly closed the connection.")
                break
            except Exception as e:
                if self.running:
                    print(f"Error handling UI client {addr}: {e}")
                break
        
        try:
            conn.close()
        except:
            pass

    def _process_ui_command(self, message):
        """Process commands from the UI and return response."""
        cmd_type = message.get("type")
        payload = message.get("payload", {})
        
        if cmd_type == "get_clients":
            clients = {}
            for addr, info in self.state_manager.get_all_clients().items():
                clients[str(addr)] = {
                    "name": info.get("name", "Unknown"),
                    "address": str(addr),
                    "is_active": addr == self.state_manager.get_active_client()
                }
            return {"clients": clients}
        
        elif cmd_type == "set_active_client":
            addr_str = payload.get("address")
            if addr_str:
                # Parse address string back to tuple
                try:
                    # Handle format like "('127.0.0.1', 12345)"
                    addr_str = addr_str.strip("()'\" ")
                    ip, port = addr_str.split(", ")
                    addr = (ip.strip("'\" "), int(port))
                    
                    if self.state_manager.set_active_client(addr):
                        return {"success": True, "message": f"Active client set to {addr}"}
                    else:
                        return {"success": False, "message": "Client not found"}
                except Exception as e:
                    return {"success": False, "message": f"Invalid address format: {e}"}
        
        elif cmd_type == "get_active_client":
            active = self.state_manager.get_active_client()
            return {"active_client": str(active) if active else None}
        
        elif cmd_type == "get_frame":
            active = self.state_manager.get_active_client()
            if active:
                frame = self.state_manager.get_latest_frame(active)
                if frame is not None:
                    # Encode frame as JPEG for transmission
                    _, img_encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    frame_data = base64.b64encode(img_encoded.tobytes()).decode('utf-8')
                    return {"frame": frame_data, "has_frame": True}
            return {"frame": None, "has_frame": False}
        
        return {"error": f"Unknown command: {cmd_type}"}

    def _handle_client(self, conn, addr):
        while self.running:
            try:
                data = conn.recv(4096)
                if not data:
                    print(f"Client {addr} disconnected.")
                    self._remove_client(addr)
                    break
                message = parse_message(data)
                if message["type"] == MessageType.CLIENT_HELLO:
                    client_name = message['payload'].get('name', 'Unknown')
                    client_video_port = message['payload'].get('video_port')
                    print(f"Client {addr} ({client_name}) sent hello. Video port: {client_video_port}")
                    self.state_manager.add_client(addr, {"conn": conn, "name": client_name, "video_port": client_video_port})
                    # Optionally set this client as active if it's the first one
                    if not self.state_manager.get_active_client():
                        self.state_manager.set_active_client(addr)

            except ConnectionResetError:
                print(f"Client {addr} forcibly closed the connection.")
                self._remove_client(addr)
                break
            except Exception as e:
                if self.running:
                    print(f"Error handling client {addr}: {e}")
                self._remove_client(addr)
                break

    def _receive_video_streams(self):
        # Structured frame assembly: {client_addr: {frame_id: {chunks: {chunk_num: data}, total_chunks: int}}}
        frame_assembly = {}
        
        while self.running:
            try:
                data, addr = self.video_socket.recvfrom(65536) # Max UDP packet size
                
                # Parse chunk metadata: frame_id(4) + chunk_num(2) + total_chunks(2) + data
                if len(data) < 8:
                    print(f"❌ Received malformed chunk from {addr}: too short ({len(data)} bytes)")
                    continue
                    
                frame_id = int.from_bytes(data[0:4], 'big')
                chunk_num = int.from_bytes(data[4:6], 'big') 
                total_chunks = int.from_bytes(data[6:8], 'big')
                chunk_data = data[8:]
                
                print(f"Received chunk {chunk_num}/{total_chunks} for frame {frame_id} from {addr} ({len(chunk_data)} bytes)")
                
                # Find which client this video data belongs to
                client_addr = None
                for k, v in self.state_manager.get_all_clients().items():
                    if k[0] == addr[0]: 
                        client_addr = k
                        break
                
                if not client_addr:
                    print(f"❌ No matching client found for video data from {addr}")
                    continue
                
                # Initialize frame assembly structures
                if client_addr not in frame_assembly:
                    frame_assembly[client_addr] = {}
                if frame_id not in frame_assembly[client_addr]:
                    frame_assembly[client_addr][frame_id] = {"chunks": {}, "total_chunks": total_chunks}
                
                # Store chunk data
                frame_assembly[client_addr][frame_id]["chunks"][chunk_num] = chunk_data
                
                # Check if frame is complete
                frame_info = frame_assembly[client_addr][frame_id]
                if len(frame_info["chunks"]) == frame_info["total_chunks"]:
                    # All chunks received, assemble frame
                    complete_frame_data = bytearray()
                    for i in range(1, frame_info["total_chunks"] + 1):
                        if i in frame_info["chunks"]:
                            complete_frame_data.extend(frame_info["chunks"][i])
                        else:
                            print(f"❌ Missing chunk {i} for frame {frame_id}")
                            break
                    else:
                        # All chunks found, decode frame
                        try:
                            np_arr = np.frombuffer(complete_frame_data, np.uint8)
                            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                            if frame is not None:
                                print(f"✅ Successfully decoded frame {frame_id} from {client_addr}. Shape: {frame.shape}")
                                self.state_manager.update_latest_frame(client_addr, frame)
                                
                                # Forward to UI if this is the active client
                                if self.state_manager.get_active_client() == client_addr:
                                    try:
                                        self._forward_frame_to_ui(complete_frame_data, frame_id)
                                    except Exception as e:
                                        print(f"Error forwarding frame to UI: {e}")
                            else:
                                print(f"❌ Failed to decode frame {frame_id} from {client_addr}")
                        except Exception as e:
                            print(f"❌ Exception decoding frame {frame_id}: {e}")
                    
                    # Clean up completed frame
                    del frame_assembly[client_addr][frame_id]
                
                # Cleanup old incomplete frames (prevent memory leak)
                current_time = int(time.time() * 1000) % 100000
                for fid in list(frame_assembly[client_addr].keys()):
                    if abs(current_time - fid) > 5000:  # Remove frames older than 5 seconds
                        del frame_assembly[client_addr][fid]

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error receiving video stream: {e}")
                break

    def _forward_frame_to_ui(self, frame_data, frame_id):
        """Forward frame to UI using chunking protocol to handle large frames."""
        chunk_size = 64000  # Leave room for metadata header
        total_chunks = (len(frame_data) + chunk_size - 1) // chunk_size
        
        print(f"Forwarding frame {frame_id} to UI: {len(frame_data)} bytes in {total_chunks} chunks")
        
        for i in range(0, len(frame_data), chunk_size):
            chunk_data = frame_data[i:i+chunk_size]
            chunk_num = i // chunk_size + 1
            
            # Create chunk with metadata: frame_id(4) + chunk_num(2) + total_chunks(2) + data
            chunk_header = frame_id.to_bytes(4, 'big') + chunk_num.to_bytes(2, 'big') + total_chunks.to_bytes(2, 'big')
            chunk_with_header = chunk_header + chunk_data
            
            self.video_socket.sendto(chunk_with_header, ('localhost', self.ui_video_port))
            # print(f"Sent chunk {chunk_num}/{total_chunks} to UI: {len(chunk_data)} bytes")

    def get_latest_frame(self, client_addr):
        return self.state_manager.get_latest_frame(client_addr)

    def _remove_client(self, addr):
        client_info = self.state_manager.get_client_info(addr)
        if client_info and "conn" in client_info:
            try:
                client_info["conn"].close()
                print(f"Closed connection for client {addr}")
            except Exception as e:
                print(f"Error closing client connection {addr}: {e}")

        self.state_manager.remove_client(addr)
        print(f"Removed client {addr}")
        if self.state_manager.get_active_client() == addr:
            self.state_manager.set_active_client(None)
            print("Active client disconnected. No active client now.")

    def _send_server_ack(self, conn):
        ack_message = create_message(MessageType.SERVER_ACK, {"status": "connected"})
        conn.sendall(ack_message)

    def set_active_client(self, addr):
        if self.state_manager.set_active_client(addr):
            print(f"Active client set to {addr}")
            # Notify all clients about the active client change (optional for Phase 1)
            for client_addr, client_info in self.state_manager.get_all_clients().items():
                try:
                    switch_msg = create_message(MessageType.SWITCH_CLIENT, {"active_client": str(addr)})
                    client_info["conn"].sendall(switch_msg)
                except Exception as e:
                    print(f"Error notifying client {client_addr} about active client change: {e}")
            return True
        else:
            print(f"Client {addr} not found.")
            return False

    def _start_input_listeners(self):
        self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self.keyboard_listener.start()
        self.mouse_listener = mouse.Listener(on_click=self._on_mouse_click, on_scroll=self._on_mouse_scroll, on_move=self._on_mouse_move)
        self.mouse_listener.start()
        print("Started keyboard and mouse listeners.")

    def _on_key_press(self, key):
        try:
            key_char = key.char if hasattr(key, 'char') else str(key)
            self._send_input_event(MessageType.KEY_EVENT, {"event_type": "press", "key": key_char})
        except AttributeError:
            self._send_input_event(MessageType.KEY_EVENT, {"event_type": "press", "key": str(key)})

    def _on_key_release(self, key):
        try:
            key_char = key.char if hasattr(key, 'char') else str(key)
            self._send_input_event(MessageType.KEY_EVENT, {"event_type": "release", "key": key_char})
        except AttributeError:
            self._send_input_event(MessageType.KEY_EVENT, {"event_type": "release", "key": str(key)})

    def _on_mouse_click(self, x, y, button, pressed):
        self._send_input_event(MessageType.MOUSE_EVENT, {"event_type": "click", "x": x, "y": y, "button": str(button), "pressed": pressed})

    def _on_mouse_scroll(self, x, y, dx, dy):
        self._send_input_event(MessageType.MOUSE_EVENT, {"event_type": "scroll", "x": x, "y": y, "dx": dx, "dy": dy})

    def _on_mouse_move(self, x, y):
        # This can generate a lot of events, consider throttling or only sending relative movements
        self._send_input_event(MessageType.MOUSE_EVENT, {"event_type": "move", "x": x, "y": y})

    def _send_input_event(self, event_type, payload):
        active_client_address = self.state_manager.get_active_client()
        if active_client_address and active_client_address in self.state_manager.get_all_clients():
            try:
                message = create_message(event_type, payload)
                client_info = self.state_manager.get_client_info(active_client_address)
                
                # Check if USB or Network client
                if client_info.get("type") == "USB":
                    send_framed(client_info["conn"], {"type": event_type, "payload": payload})
                else: # Network client
                    client_info["conn"].sendall(message)
            except Exception as e:
                print(f"Error sending {event_type} to active client {active_client_address}: {e}")
                self._remove_client(active_client_address)
        # else: No active client to send input to

    def _listen_for_usb_agents(self):
        """Periodically scan for new serial devices and attempt to connect."""
        print("[USB] Starting USB agent listener...")
        known_ports = set()
        while self.running:
            try:
                available_ports = {p.device for p in serial.tools.list_ports.comports()}
                new_ports = available_ports - known_ports

                for port in new_ports:
                    print(f"[USB] New serial port detected: {port}")
                    # Give the OS a moment to stabilize the new port
                    time.sleep(1)
                    thread = threading.Thread(target=self._handle_usb_client, args=(port,), daemon=True)
                    thread.start()

                known_ports = available_ports
            except Exception as e:
                print(f"[USB] Error scanning for serial ports: {e}")
            
            time.sleep(5) # Scan every 5 seconds
    
    def _handle_usb_client(self, port):
        """Handle a single USB client connection, from handshake to termination."""
        print(f"[USB] Attempting to handshake with agent on {port}...")
        try:
            conn = serial.Serial(port, baudrate=115200, timeout=2)
        except serial.SerialException as e:
            print(f"[USB] Failed to open port {port}: {e}")
            return

        client_id = f"USB:{port}"

        try:
            # Handshake
            handshake_payload = {"magic": "NETKVM_SERVER_HELLO"}
            if not send_framed(conn, {"type": "handshake", "payload": handshake_payload}):
                conn.close()
                return

            response = receive_framed(conn)
            if not response or response.get("payload", {}).get("magic") != "NETKVM_CLIENT_HELLO":
                print(f"[USB] Handshake failed on {port}. Closing.")
                conn.close()
                return

            client_name = response['payload'].get('name', 'USB Agent')
            print(f"[USB] Handshake successful with {client_name} on {port}")
            self.state_manager.add_client(client_id, {"conn": conn, "name": client_name, "type": "USB"})

            # Main communication loop
            while self.running and client_id in self.state_manager.get_all_clients():
                message = receive_framed(conn)
                if message is None:
                    # null message means disconnection or error
                    print(f"[USB] Agent {client_id} disconnected.")
                    break
                
                # Here, we only expect video frames from the client
                if message.get("type") == MessageType.VIDEO_FRAME:
                    frame_data = base64.b64decode(message["payload"]["frame"])
                    np_arr = np.frombuffer(frame_data, np.uint8)
                    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        self.state_manager.update_latest_frame(client_id, frame)
                else:
                    print(f"[USB] Received unexpected message from {client_id}: {message.get('type')}")

        except Exception as e:
            print(f"[USB] Error handling client {client_id}: {e}")
        finally:
            self._remove_client(client_id)
            if conn.is_open:
                conn.close()
            print(f"[USB] Closed connection on {port}")

    def stop(self):
        self.running = False
        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener.join()
        if self.mouse_listener:
            self.mouse_listener.stop()
            self.mouse_listener.join()

        # Close all client connections
        for addr, client_info in list(self.state_manager.get_all_clients().items()):
            if "conn" in client_info:
                try:
                    client_info["conn"].close()
                except Exception as e:
                    print(f"Error closing client connection {addr} during shutdown: {e}")

        if self.server_socket:
            self.server_socket.close()
        if self.video_socket:
            self.video_socket.close()
        if self.ui_control_socket:
            self.ui_control_socket.close()
        print("Server stopped.")

def main():
    print("[INFO] Initializing server...")
    server = None
    try:
        server = CentralHubServer()
        print("[INFO] Starting server...")
        server.start()
        print("[SUCCESS] Server has started successfully.")
        while True:
            time.sleep(1) # Keep main thread alive
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down server...")
    except Exception as e:
        print(f"[CRITICAL] Server failed to start or run: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if server and server.running:
            server.stop()

if __name__ == "__main__":
    main()