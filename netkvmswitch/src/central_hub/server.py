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
import av

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.protocol import MessageType, create_message, parse_message
from common.serial_protocol import send_framed, receive_framed
from common.config import config
from .state_manager import StateManager

def recv_all(sock, n):
    """Helper function to receive n bytes from a socket."""
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return data

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
        self.input_forwarding_enabled = True

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
            
            if self.host in ['127.0.0.1', 'localhost']:
                context.verify_mode = ssl.CERT_NONE
                context.check_hostname = False
            else:
                context.verify_mode = ssl.CERT_REQUIRED
                context.check_hostname = False

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        if config.security.use_tls:
            self.server_socket = context.wrap_socket(self.server_socket, server_side=True)

        self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.video_socket.bind((self.host, self.video_port))
        
        self.ui_video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ui_video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ui_video_socket.bind((self.host, self.ui_video_port))

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
                print(f"Accepted connection from {addr}")
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
                self._send_server_ack(conn)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error accepting connections: {e}")
                break

    def _accept_ui_connections(self):
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
                try:
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
                    _, img_encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    frame_data = base64.b64encode(img_encoded.tobytes()).decode('utf-8')
                    return {"frame": frame_data, "has_frame": True}
            return {"frame": None, "has_frame": False}
        
        elif cmd_type == "set_input_forwarding":
            enabled = payload.get("enabled", False)
            self.input_forwarding_enabled = bool(enabled)
            print(f"Input forwarding {'enabled' if self.input_forwarding_enabled else 'disabled'}.")
            return {"success": True, "enabled": self.input_forwarding_enabled}
            
        elif cmd_type == "shutdown_active_client":
            active_client_addr = self.state_manager.get_active_client()
            if active_client_addr:
                client_info = self.state_manager.get_client_info(active_client_addr)
                if client_info and client_info.get("type") != "USB":
                    try:
                        shutdown_msg = create_message(MessageType.SHUTDOWN, {})
                        client_info["conn"].sendall(shutdown_msg)
                        return {"success": True, "message": f"Shutdown signal sent to {active_client_addr}"}
                    except Exception as e:
                        return {"success": False, "message": f"Failed to send shutdown signal: {e}"}
                else:
                    return {"success": False, "message": "Active client is a USB device or not found."}
            else:
                return {"success": False, "message": "No active client to shut down."}

        elif cmd_type == "restart_agent":
            addr_str = payload.get("address")
            if addr_str:
                try:
                    addr_str = addr_str.strip("()'\" ")
                    ip, port = addr_str.split(", ")
                    addr = (ip.strip("'\" "), int(port))
                    
                    client_info = self.state_manager.get_client_info(addr)
                    if client_info:
                        restart_msg = create_message(MessageType.RESTART, {})
                        client_info["conn"].sendall(restart_msg)
                        return {"success": True, "message": f"Restart signal sent to {addr}"}
                    else:
                        return {"success": False, "message": "Client not found"}
                except Exception as e:
                    return {"success": False, "message": f"Invalid address or failed to send: {e}"}
        
        elif cmd_type == "forward_io_event":
            target_address_str = payload.get("address")
            event_type = payload.get("event_type")
            event_payload = payload.get("payload")
            
            try:
                addr_str = target_address_str.strip("()'\" ")
                ip, port = addr_str.split(", ")
                target_address = (ip.strip("'\" "), int(port))
                
                self._send_input_event_to_client(target_address, event_type, event_payload)
                return {"success": True}
            except Exception as e:
                return {"success": False, "message": str(e)}

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
        client_addr = self.state_manager.find_client_by_ip(addr[0])

        if not client_addr:
            print(f"Error: Could not find matching control client for video connection from {addr}. Dropping.")
            conn.close()
            return
            
        print(f"Associated video connection from {addr} with control client {client_addr}")
        self.state_manager.add_video_socket(client_addr, conn)

        try:
            while self.running:
                size_bytes = recv_all(conn, 4)
                if not size_bytes:
                    print(f"Video client {addr} disconnected (no header).")
                    break
                
                frame_size = int.from_bytes(size_bytes, 'big')

                if frame_size <= 0 or frame_size > 20 * 1024 * 1024:
                    print(f"Invalid frame size received from {addr}: {frame_size}")
                    break

                frame_data = recv_all(conn, frame_size)
                if not frame_data:
                    print(f"Video client {addr} disconnected (incomplete frame).")
                    break
                
                packet = av.Packet(frame_data)
                
                self._forward_packet_to_ui(client_addr, packet)

        except ConnectionResetError:
            print(f"Video connection from {addr} was forcibly closed.")
        except Exception as e:
            print(f"Error during video streaming from {addr}: {e}")
        finally:
            print(f"Closing video connection from {addr}")
            self.state_manager.remove_video_socket(client_addr)
            conn.close()

    def _forward_packet_to_ui(self, client_addr, packet):
        with self.ui_video_clients_lock:
            disconnected_clients = []
            
            addr_str = str(client_addr)
            addr_bytes = addr_str.encode('utf-8')
            padded_addr = addr_bytes.ljust(40)

            h264_data = bytes(packet)

            message_to_send = padded_addr + h264_data
            
            size_header = len(message_to_send).to_bytes(4, 'big')
            full_message = size_header + message_to_send

            for ui_conn in self.ui_video_clients:
                try:
                    ui_conn.sendall(full_message)
                except (ConnectionResetError, BrokenPipeError):
                    print("UI video client disconnected.")
                    disconnected_clients.append(ui_conn)
            
            for client in disconnected_clients:
                self.ui_video_clients.remove(client)

    def _accept_ui_video_connections(self):
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
        self._send_input_event(MessageType.MOUSE_EVENT, {"event_type": "move", "x": x, "y": y})

    def _send_input_event(self, event_type, payload):
        if not self.input_forwarding_enabled:
            return

        active_client_address = self.state_manager.get_active_client()
        if active_client_address:
            self._send_input_event_to_client(active_client_address, event_type, payload)

    def _send_input_event_to_client(self, client_address, event_type, payload):
        if not self.input_forwarding_enabled:
            return

        if client_address in self.state_manager.get_all_clients():
            try:
                message = create_message(event_type, payload)
                client_info = self.state_manager.get_client_info(client_address)
                
                if client_info.get("type") == "USB":
                    send_framed(client_info["conn"], {"type": event_type, "payload": payload})
                else:
                    client_info["conn"].sendall(message)
            except Exception as e:
                print(f"Error sending {event_type} to client {client_address}: {e}")
                self._remove_client(client_address)

    def _listen_for_usb_agents(self):
        print("[USB] Starting USB agent listener...")
        known_ports = set()
        while self.running:
            try:
                available_ports = {p.device for p in serial.tools.list_ports.comports()}
                new_ports = available_ports - known_ports

                for port in new_ports:
                    print(f"[USB] New serial port detected: {port}")
                    time.sleep(1)
                    thread = threading.Thread(target=self._handle_usb_client, args=(port,), daemon=True)
                    thread.start()

                known_ports = available_ports
            except Exception as e:
                print(f"[USB] Error scanning for serial ports: {e}")
            
            time.sleep(5)
    
    def _handle_usb_client(self, port):
        print(f"[USB] Attempting to handshake with agent on {port}...")
        try:
            conn = serial.Serial(port, baudrate=115200, timeout=2)
        except serial.SerialException as e:
            print(f"[USB] Failed to open port {port}: {e}")
            return

        client_id = f"USB:{port}"

        try:
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

            while self.running and client_id in self.state_manager.get_all_clients():
                message = receive_framed(conn)
                if message is None:
                    print(f"[USB] Agent {client_id} disconnected.")
                    break
                
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
            time.sleep(1)
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
