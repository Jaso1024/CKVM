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

from common.protocol import MessageType, create_message, parse_message
from common.serial_protocol import send_framed, receive_framed
from common.config import config
from .state_manager import StateManager

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
        self.ui_video_clients = []
        self.ui_video_clients_lock = threading.Lock()

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
            
            # For localhost testing, be more lenient with certificate verification
            if self.host in ['127.0.0.1', 'localhost']:
                context.verify_mode = ssl.CERT_NONE  # Don't require client certs for localhost
                context.check_hostname = False
            else:
                context.verify_mode = ssl.CERT_REQUIRED
                context.check_hostname = False

        # Main client connection socket (TLS)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        if config.security.use_tls:
            self.server_socket = context.wrap_socket(self.server_socket, server_side=True)

        # Video streaming socket (TCP for reliability)
        self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.video_socket.bind((self.host, self.video_port))
        
        # UI video forwarding socket (NOW TCP)
        self.ui_video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ui_video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ui_video_socket.bind((self.host, self.ui_video_port))

        # UI control socket (TCP, no TLS for local communication)
        self.ui_control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ui_control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ui_control_socket.bind((self.host, self.ui_control_port))
        self.ui_control_socket.listen(5)

        self.running = True
        print(f"Server listening on:")
        print(f"  Client connections: {self.host}:{self.port} (TCP{'S' if config.security.use_tls else ''})")
        print(f"  Video streams: {self.host}:{self.video_port} (TCP)")
        print(f"  UI control: {self.host}:{self.ui_control_port} (TCP)")
        print(f"  UI video: {self.host}:{self.ui_video_port} (TCP)")

        threading.Thread(target=self._accept_connections, daemon=True).start()
        threading.Thread(target=self._accept_ui_connections, daemon=True).start()
        threading.Thread(target=self._accept_video_connections, daemon=True).start()
        threading.Thread(target=self._accept_ui_video_connections, daemon=True).start()
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

    def _accept_video_connections(self):
        """Accept TCP video connections from clients."""
        self.video_socket.listen(10)
        print(f"Video server listening on {self.host}:{self.video_port} (TCP)")
        
        while self.running:
            try:
                conn, addr = self.video_socket.accept()
                print(f"Video connection from {addr}")
                threading.Thread(target=self._handle_video_connection, args=(conn, addr), daemon=True).start()
            except Exception as e:
                if self.running:
                    print(f"Error accepting video connection: {e}")
                break

    def _handle_video_connection(self, conn, addr):
        """Handle TCP video stream from a client and forward it."""
        client_control_addr = None
        try:
            # First, we need to associate this video connection with a control connection
            # The client should send a HELLO message on the control connection that includes its video port
            # For now, we'll find the client by matching the IP and hoping the port is right.
            # A better approach would be a proper handshake.
            
            # Simplified: Find client by IP. This assumes one client per IP.
            for c_addr, info in self.state_manager.get_all_clients().items():
                if c_addr[0] == addr[0]:
                    client_control_addr = c_addr
                    info['video_conn'] = conn
                    print(f"Associated video connection {addr} with control connection {c_addr}")
                    break

            if not client_control_addr:
                print(f"Could not find a matching control client for video connection {addr}. Closing.")
                return

            while self.running:
                # Read H.264 packets and forward them
                # PyAV's h264 container format sends raw packets. We can read in chunks.
                packet = conn.recv(4096)
                if not packet:
                    print(f"Video stream from {addr} ended.")
                    break
                
                # Forward this packet to all connected UI clients
                # Add logging here to confirm packet reception and forwarding
                print(f"Received {len(packet)} bytes video packet from {addr}. Forwarding to UI clients.")
                self._forward_packet_to_ui(packet)

        except (ConnectionResetError, BrokenPipeError):
            print(f"Video connection from {addr} lost.")
        except Exception as e:
            print(f"Error handling video from {addr}: {e}")
        finally:
            if client_control_addr:
                self.state_manager.get_client_info(client_control_addr).pop('video_conn', None)
            conn.close()
            print(f"Closed video connection from {addr}")

    def _forward_packet_to_ui(self, packet):
        """Forward a raw video packet to all connected UI clients."""
        with self.ui_video_clients_lock:
            disconnected_clients = []
            for ui_conn in self.ui_video_clients:
                try:
                    ui_conn.sendall(packet)
                except (ConnectionResetError, BrokenPipeError):
                    print("UI video client disconnected.")
                    disconnected_clients.append(ui_conn)
                except Exception as e:
                    print(f"Error sending packet to UI client: {e}")
                    disconnected_clients.append(ui_conn)
            
            # Clean up disconnected clients
            for client in disconnected_clients:
                self.ui_video_clients.remove(client)

    def _accept_ui_video_connections(self):
        """Accept TCP connections from the UI for video streaming."""
        self.ui_video_socket.listen(5)
        while self.running:
            try:
                conn, addr = self.ui_video_socket.accept()
                print(f"UI video client connected from {addr}")
                with self.ui_video_clients_lock:
                    self.ui_video_clients.append(conn)
            except Exception as e:
                if self.running:
                    print(f"Error accepting UI video connection: {e}")
                break

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
        if self.ui_video_socket:
            self.ui_video_socket.close()
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