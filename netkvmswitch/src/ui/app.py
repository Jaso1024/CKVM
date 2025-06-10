import streamlit as st
import time
import sys
import os
import cv2
import numpy as np
import socket
import threading
from multiprocessing import Process, Queue
import av # New import for real-time decoding
import logging

# Add the src directory to the path so we can import our modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from common.protocol import create_message, parse_message
from common.config import config
from central_hub.hub_runner import run_hub_process
from source_agent.agent_runner import run_agent_process

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - UI - %(message)s')

def recv_all(sock, n):
    """Helper function to receive n bytes from a socket."""
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return data

# --- Process Management ---
def manage_process(process_key, target, args=()):
    process = st.session_state.get(process_key)
    if process and process.is_alive():
        return # Process is already running
        
    # Terminate any old process before starting a new one
    if process:
        process.terminate()
        process.join()

    # Start a new process
    process = Process(target=target, args=args)
    process.daemon = True
    process.start()
    st.session_state[process_key] = process

def stop_process(process_key):
    process = st.session_state.get(process_key)
    if process and process.is_alive():
        process.terminate()
        process.join(timeout=5)
        st.session_state[process_key] = None

# --- UI Application Logic ---
class NetKVMUI:
    def __init__(self):
        self.control_socket = None
        self.video_socket = None
        self.connected = False
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.clients = {}
        self.active_client = None
        
        # Initialize session state
        if 'ui_initialized' not in st.session_state:
            st.session_state.ui_initialized = True
            st.session_state.server_running = False
            st.session_state.connected_to_server = False
    
    def start_server_if_needed(self):
        """Start the server if it's not running and auto_start is enabled."""
        if config.ui.auto_start_server and not st.session_state.server_running:
            try:
                # Try to start the server
                cmd = [sys.executable, "-m", "central_hub.server"]
                self.server_process = subprocess.Popen(
                    cmd,
                    cwd=os.path.join(os.path.dirname(__file__), '..'),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                st.session_state.server_running = True
                st.success("Server started successfully!")
                time.sleep(2)  # Give server time to start
                return True
            except Exception as e:
                st.error(f"Failed to start server: {e}")
                return False
        return st.session_state.server_running
    
    def connect_to_server(self):
        """Connect to the server's UI control interface."""
        if self.connected:
            return True
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.connect((config.ui.server_host, config.server.ui_control_port))
            
            # Connect to the new TCP video stream
            self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.video_socket.connect((config.ui.server_host, config.server.ui_video_port))

            self.connected = True
            threading.Thread(target=self._receive_video_stream, daemon=True).start()
            return True
        except Exception as e:
            st.error(f"Failed to connect to Hub at {config.ui.server_host}:{config.server.ui_control_port}. Is it running?")
            return False

    def disconnect_from_server(self):
        self.connected = False
        if self.control_socket: self.control_socket.close()
        if self.video_socket: self.video_socket.close()

    def send_command(self, command_type, payload=None):
        if not self.connected: return None
        try:
            message = create_message(command_type, payload or {})
            self.control_socket.sendall(message)
            data = self.control_socket.recv(4096)
            return parse_message(data).get('payload', {}) if data else None
        except Exception:
            self.disconnect_from_server()
            return None

    def get_clients(self):
        response = self.send_command("get_clients")
        self.clients = response.get('clients', {}) if response else {}
        return self.clients

    def set_active_client(self, address):
        self.send_command("set_active_client", {"address": address})
    
    def get_active_client(self):
        response = self.send_command("get_active_client")
        self.active_client = response.get('active_client') if response else None
        return self.active_client
        
    def _receive_video_stream(self):
        """Receives length-prefixed H.264 frames and decodes them."""
        codec = av.CodecContext.create('h264', 'r')
        
        while self.connected:
            try:
                # 1. Read the 4-byte frame size header
                frame_size_bytes = recv_all(self.video_socket, 4)
                if not frame_size_bytes:
                    logging.warning("Connection closed by server.")
                    break
                
                frame_size = int.from_bytes(frame_size_bytes, 'big')

                # 2. Read the full frame data
                frame_data = recv_all(self.video_socket, frame_size)
                if not frame_data:
                    logging.error(f"Incomplete frame received. Expected {frame_size} bytes, but connection closed.")
                    break
                
                logging.info(f"Received complete frame of {frame_size} bytes.")

                # 3. Decode the frame
                packets = codec.parse(frame_data)
                if not packets:
                    logging.warning("Could not parse any packets from the received frame data.")
                    continue

                for packet in packets:
                    frames = codec.decode(packet)
                    for frame in frames:
                        img = frame.to_ndarray(format='bgr24')
                        with self.frame_lock:
                            self.latest_frame = img
            
            except (ConnectionResetError, BrokenPipeError):
                logging.warning("Video connection to server was lost.")
                break
            except Exception as e:
                logging.error(f"Video reception/decoding error: {e}", exc_info=True)
                # Reset codec on error to handle potential corruption
                codec = av.CodecContext.create('h264', 'r')
                continue

        logging.info("Video receiver thread stopped.")

    def get_latest_frame(self):
        with self.frame_lock:
            return self.latest_frame

    def cleanup(self):
        """Cleanup resources."""
        self.disconnect_from_server()
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            except:
                try:
                    self.server_process.kill()
                except:
                    pass

# --- UI Views ---
def draw_receiver_mode():
    st.header("Receiver Mode (Central Hub)")
    
    if 'hub_process' not in st.session_state:
        st.session_state.hub_process = None
    
    if st.session_state.hub_process and st.session_state.hub_process.is_alive():
        st.success("✅ Hub Process is Running")
        if st.button("Stop Hub", use_container_width=True):
            stop_process('hub_process')
            st.rerun()

        # UI Controller for receiver
        if 'receiver_ui' not in st.session_state:
            st.session_state.receiver_ui = NetKVMUI()
        
        ui = st.session_state.receiver_ui
        
        if not ui.connected:
            if st.button("Connect to Hub", use_container_width=True):
                if ui.connect_to_server():
                    st.rerun()
        else:
            st.info("🔌 Connected to Hub Interface")
            
            # The rest of the receiver UI
            clients = ui.get_clients()
            active_client = ui.get_active_client()
            
            st.sidebar.subheader("Connected Clients")
            if st.sidebar.button("Refresh", use_container_width=True):
                st.rerun()

            for addr, info in clients.items():
                if st.sidebar.button(f"{info.get('name')} ({'Active' if info.get('is_active') else 'Idle'})", key=addr):
                    ui.set_active_client(addr)
                    st.rerun()
            
            frame = ui.get_latest_frame()
            if frame is not None:
                print(f"🖼️ UI: Displaying frame with shape {frame.shape}")
                st.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), use_container_width=True)
            else:
                print("⏳ UI: No frame available, showing placeholder")
                st.image(np.zeros((480, 640, 3), dtype=np.uint8), caption="Waiting for video...", use_container_width=True)
            
            time.sleep(0.05)
            st.rerun()
            
    else:
        st.info("Hub is not running.")
        if st.button("Start Hub", use_container_width=True):
            manage_process('hub_process', run_hub_process)
            time.sleep(2) # give it time to start
            st.rerun()

def draw_sender_mode():
    st.header("Sender Mode (Source Agent)")
    
    if 'agent_process' not in st.session_state:
        st.session_state.agent_process = None

    if st.session_state.agent_process and st.session_state.agent_process.is_alive():
        st.error("❌ Agent is Running")
        if st.button("Stop Sending", use_container_width=True):
            stop_process('agent_process')
            st.rerun()
    else:
        st.success("✅ Agent is Stopped")
        connection_type = st.radio("Connection Type", ['Network', 'USB'])
        
        settings = {}
        if connection_type == 'Network':
            settings['server_host'] = st.text_input("Hub IP Address", value=config.client.server_host)
        elif connection_type == 'USB':
            settings['port'] = st.text_input("COM Port (optional, leave blank to scan)")

        if st.button("Start Sending", use_container_width=True):
            manage_process('agent_process', run_agent_process, args=(connection_type, settings))
            st.rerun()

def main():
    st.set_page_config(page_title="NetKVMSwitch", layout="wide")
    st.sidebar.title("NetKVMSwitch")

    if 'app_mode' not in st.session_state:
        st.session_state.app_mode = "Home"

    app_mode = st.sidebar.radio(
        "Choose Operating Mode",
        ("Home", "Receiver Mode", "Sender Mode"),
        key='app_mode_selector'
    )
    st.session_state.app_mode = app_mode

    if st.session_state.app_mode == "Receiver Mode":
        draw_receiver_mode()
    elif st.session_state.app_mode == "Sender Mode":
        draw_sender_mode()
    else: # Home
        st.title("Welcome to NetKVMSwitch")
        st.write("Please select a mode from the sidebar to begin.")
        st.info(
            "**Receiver Mode:** Turns this computer into the central hub, allowing you to view and control other machines.\n\n"
            "**Sender Mode:** Turns this computer into a source, streaming its screen to a receiver hub."
        )

if __name__ == "__main__":
    # Cleanup on exit
    import atexit
    
    def cleanup():
        if 'ui_controller' in st.session_state:
            st.session_state.ui_controller.cleanup()
    
    atexit.register(cleanup)
    main()