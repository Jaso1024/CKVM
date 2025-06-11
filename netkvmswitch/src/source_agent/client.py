# Main client logic, network, K/M injection

import socket
import threading
import time
import cv2
import numpy as np
from pynput.keyboard import Controller as KeyboardController, Key
from pynput.mouse import Controller as MouseController, Button
import ssl
import sys
import os
import logging
import platform
import av
from multiprocessing import Process, Queue, shared_memory, Value

from mss import mss
from source_agent.screen_capture import ScreenCapturer

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.protocol import create_message, parse_message, MessageType
from common.config import config
from pynput import mouse, keyboard

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

def video_pipeline_process(running_flag, encoded_packet_queue, shm_name, frame_shape, frame_dtype):
    """
    A separate process to handle the entire video pipeline (capture, encode)
    to bypass the GIL and improve performance.
    """
    import queue
    
    # Attach to the shared memory block
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    frame_buffer = np.ndarray(frame_shape, dtype=frame_dtype, buffer=existing_shm.buf)

    # --- Inner functions for capture and encode ---
    def capture_frames():
        capturer = ScreenCapturer()
        target_width, target_height = frame_shape[1], frame_shape[0]
        frame_interval = 1.0 / 60.0

        while running_flag.value:
            try:
                raw_frame = capturer.capture_frame()
                if raw_frame is None: continue

                if (raw_frame.shape[1], raw_frame.shape[0]) != (target_width, target_height):
                    frame = cv2.resize(raw_frame, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
                else:
                    frame = raw_frame
                
                # Write directly to shared memory
                np.copyto(frame_buffer, frame)

                time.sleep(frame_interval)
            except Exception as e:
                logging.error(f"[CaptureProcess] Error: {e}")
                time.sleep(0.1)

    def encode_frames():
        try:
            container = av.open('dummy', mode='w', format='h264')
            stream = container.add_stream('h264', rate=60)
            stream.width, stream.height = frame_shape[1], frame_shape[0]
            stream.pix_fmt = 'yuv420p'
            stream.options = {
                'crf': '23', 'preset': 'veryfast', 'tune': 'zerolatency',
                'hwaccel': 'auto', 'flags': 'low_delay'
            }

            while running_flag.value:
                try:
                    # Read from shared memory
                    frame = np.copy(frame_buffer)
                    av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
                    
                    packets = stream.encode(av_frame)
                    if packets:
                        packet_data = b"".join(bytes(p) for p in packets)
                        if packet_data:
                            encoded_packet_queue.put(packet_data)
                    
                    time.sleep(0.001) # Yield
                except Exception as e:
                    logging.error(f"[EncodeProcess] Error: {e}")
                    time.sleep(0.1)
        except Exception as e:
            logging.error(f"[EncodeProcess] Initialization failed: {e}")

    # Start capture and encode threads within the process
    capture_thread = threading.Thread(target=capture_frames, daemon=True)
    encode_thread = threading.Thread(target=encode_frames, daemon=True)
    capture_thread.start()
    encode_thread.start()
    capture_thread.join()
    encode_thread.join()
    
    existing_shm.close()

class SourceAgentClient:
    def __init__(self, server_host=None, server_port=None, video_port=None, client_name=None):
        self.server_host = server_host or config.client.server_host
        self.server_port = server_port or config.client.server_port
        self.video_port = video_port or config.client.video_port
        self.client_name = client_name or config.client.client_name
        self.running = False
        self.control_socket = None
        self.video_socket = None
        self.video_process = None
        self.shared_memory = None
        self.running_flag = None

        self.keyboard_controller = KeyboardController()
        self.mouse_controller = MouseController()

    def start(self):
        self.running = True
        server_ip = self.server_host
        
        if not self._connect_to_server(server_ip):
            return

        self._start_streaming()
        self._start_message_handler()
        logging.info("Source Agent started and connected to server.")

    def stop(self):
        self.running = False
        if self.running_flag:
            self.running_flag.value = False
        if self.video_process:
            self.video_process.join(timeout=2)
            if self.video_process.is_alive():
                self.video_process.terminate()
        if self.shared_memory:
            self.shared_memory.close()
            self.shared_memory.unlink()
        if self.control_socket: self.control_socket.close()
        if self.video_socket: self.video_socket.close()
        logging.info("Source Agent stopped.")

    def _connect_to_server(self, server_ip):
        try:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            certs_dir = config.get_certs_dir()
            context.load_cert_chain(
                certfile=os.path.join(certs_dir, config.security.client_cert), 
                keyfile=os.path.join(certs_dir, config.security.client_key)
            )
            if server_ip in ['127.0.0.1', 'localhost']:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            else:
                context.load_verify_locations(os.path.join(certs_dir, config.security.ca_cert))
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket = context.wrap_socket(sock, server_hostname=server_ip)
            self.control_socket.connect((server_ip, self.server_port))
            logging.info(f"Control connection established with {server_ip}:{self.server_port}")

            hello_msg = create_message(MessageType.CLIENT_HELLO, {"name": self.client_name, "video_port": self.video_port})
            self.control_socket.sendall(hello_msg)
            logging.info(f"Sent CLIENT_HELLO to server with name: {self.client_name}")
            
            time.sleep(0.5)
            
            self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.video_socket.connect((server_ip, self.video_port))
            logging.info(f"Video connection established with {server_ip}:{self.video_port}")
            
            return True
        except Exception as e:
            logging.error(f"Failed to connect to server: {e}")
            return False

    def _start_streaming(self):
        frame_shape = (720, 1280, 3)
        frame_dtype = np.uint8
        frame_size = int(np.prod(frame_shape) * np.dtype(frame_dtype).itemsize)
        
        # Generate a unique name for the shared memory block
        shm_name = f'netkvm_frame_buffer_{os.getpid()}_{time.time()}'

        # Create the new shared memory block
        self.shared_memory = shared_memory.SharedMemory(name=shm_name, create=True, size=frame_size)

        encoded_packet_queue = Queue()
        self.running_flag = Value('b', True)

        self.video_process = Process(
            target=video_pipeline_process,
            args=(self.running_flag, encoded_packet_queue, self.shared_memory.name, frame_shape, frame_dtype)
        )
        self.video_process.daemon = True
        self.video_process.start()

        network_thread = threading.Thread(target=self._network_sender, args=(encoded_packet_queue,), daemon=True)
        network_thread.start()

    def _network_sender(self, encoded_packet_queue):
        import queue
        while self.running:
            try:
                packet_data = encoded_packet_queue.get(timeout=1.0)
                if packet_data:
                    frame_size = len(packet_data)
                    self.video_socket.sendall(frame_size.to_bytes(4, 'big'))
                    self.video_socket.sendall(packet_data)
            except queue.Empty:
                continue
            except (ConnectionResetError, BrokenPipeError):
                logging.warning("Video connection lost.")
                self.running = False
                break
            except Exception as e:
                logging.error(f"Network sender error: {e}")
                self.running = False
                break

    def _start_message_handler(self):
        handler_thread = threading.Thread(target=self._handle_server_messages, daemon=True)
        handler_thread.start()

    def _handle_server_messages(self):
        while self.running:
            try:
                data = self.control_socket.recv(4096)
                if not data:
                    logging.warning("Server closed the connection.")
                    break
                message = parse_message(data)
                self._handle_command(message)
            except (ConnectionResetError, BrokenPipeError):
                logging.warning("Connection to server was reset.")
                break
            except Exception as e:
                if self.running: logging.error(f"Error handling server message: {e}")
                break
        self.running = False

    def _handle_command(self, message):
        msg_type = message.get("type")
        payload = message.get("payload")
        if msg_type == MessageType.KEY_EVENT: self._inject_key_event(payload)
        elif msg_type == MessageType.MOUSE_EVENT: self._inject_mouse_event(payload)

    def _inject_key_event(self, payload):
        event_type, key_str = payload["event_type"], payload["key"]
        try:
            key = getattr(Key, key_str.split('.')[-1]) if key_str.startswith('Key.') else key_str
            if event_type == "press": self.keyboard_controller.press(key)
            elif event_type == "release": self.keyboard_controller.release(key)
        except Exception as e:
            logging.error(f"Error injecting key event {key_str}: {e}")

    def _inject_mouse_event(self, payload):
        event_type = payload["event_type"]
        if event_type == "click":
            button = getattr(Button, payload["button"].split('.')[-1])
            self.mouse_controller.position = (payload["x"], payload["y"])
            if payload["pressed"]: self.mouse_controller.press(button)
            else: self.mouse_controller.release(button)
        elif event_type == "scroll": self.mouse_controller.scroll(payload["dx"], payload["dy"])
        elif event_type == "move": self.mouse_controller.position = (payload["x"], payload["y"])

def main():
    # This is required for multiprocessing to work correctly on Windows
    if sys.platform == 'win32':
        import multiprocessing
        multiprocessing.freeze_support()
        
    client = SourceAgentClient()
    try:
        client.start()
        while client.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down client...")
    finally:
        client.stop()

if __name__ == "__main__":
    main()
