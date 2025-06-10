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
import av # New import for real-time encoding

# Add FFmpeg bin directory to PATH for PyAV
ffmpeg_bin_path = r"C:\Users\jaboh\Downloads\ffmpeg-master-latest-win64-gpl-shared\ffmpeg-master-latest-win64-gpl-shared\bin"
if os.path.exists(ffmpeg_bin_path) and ffmpeg_bin_path not in os.environ['PATH']:
    os.environ['PATH'] = ffmpeg_bin_path + os.pathsep + os.environ['PATH']
    logging.info(f"Prepended FFmpeg bin path to PATH: {ffmpeg_bin_path}")
else:
    logging.warning(f"FFmpeg bin path not found or already in PATH: {ffmpeg_bin_path}")

from mss import mss
from source_agent.screen_capture import ScreenCapturer

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.protocol import create_message, parse_message, MessageType
from common.config import config
from pynput import mouse, keyboard

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SourceAgentClient:
    """
    The Source Agent client that captures the screen, mouse, and keyboard inputs
    and sends them to the Central Hub server.
    """
    def __init__(self, server_host=None, server_port=None, video_port=None, client_name=None):
        self.server_host = server_host or config.client.server_host
        self.server_port = server_port or config.client.server_port
        self.video_port = video_port or config.client.video_port
        self.client_name = client_name or config.client.client_name
        self.running = False
        self.control_socket = None
        self.video_socket = None

        self.mouse_listener = None
        self.keyboard_listener = None

    def _get_server_ip(self):
        """Placeholder for service discovery."""
        return self.server_host

    def start(self):
        """Starts the agent."""
        self.running = True
        server_ip = self._get_server_ip()
        
        if not self._connect_to_server(server_ip):
            return

        self._start_listeners()
        self._start_streaming()
        self._start_message_handler()
        logging.info("Source Agent started and connected to server.")

    def stop(self):
        """Stops the agent."""
        self.running = False
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.control_socket:
            self.control_socket.close()
        if self.video_socket:
            self.video_socket.close()
        logging.info("Source Agent stopped.")

    def _connect_to_server(self, server_ip):
        """Establishes connection to the Central Hub server."""
        try:
            # Control connection (TLS)
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            certs_dir = config.get_certs_dir()
            
            # Always load client certificate
            context.load_cert_chain(
                certfile=os.path.join(certs_dir, config.security.client_cert), 
                keyfile=os.path.join(certs_dir, config.security.client_key)
            )
            
            # For localhost testing, skip certificate verification but still use certificates
            if server_ip in ['127.0.0.1', 'localhost']:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            else:
                context.load_verify_locations(os.path.join(certs_dir, config.security.ca_cert))
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket = context.wrap_socket(sock, server_hostname=server_ip)
            self.control_socket.connect((server_ip, self.server_port))
            logging.info(f"Control connection established with {server_ip}:{self.server_port}")

            # Send CLIENT_HELLO message to register with server
            hello_msg = create_message(MessageType.CLIENT_HELLO, {
                "name": self.client_name,
                "video_port": self.video_port
            })
            self.control_socket.sendall(hello_msg)
            logging.info(f"Sent CLIENT_HELLO to server with name: {self.client_name}")
            
            # Wait a moment for the server to register the control connection
            # before establishing the video connection
            time.sleep(0.5)  # 500ms delay to prevent race condition
            
            # Video connection (TCP for reliability)
            self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.video_socket.connect((server_ip, self.video_port))
            logging.info(f"Video connection established with {server_ip}:{self.video_port}")
            
            return True
        except Exception as e:
            logging.error(f"Failed to connect to server: {e}")
            return False

    def _start_streaming(self):
        """Starts the video streaming thread."""
        stream_thread = threading.Thread(target=self._stream_video, daemon=True)
        stream_thread.start()

    def _start_message_handler(self):
        """Starts the message handling thread for server communication."""
        handler_thread = threading.Thread(target=self._handle_server_messages, daemon=True)
        handler_thread.start()

    def _handle_server_messages(self):
        """Handles messages from the server."""
        while self.running:
            try:
                data = self.control_socket.recv(4096)
                if not data:
                    logging.warning("Server closed the connection")
                    break
                    
                message = parse_message(data)
                msg_type = message.get("type")
                
                if msg_type == MessageType.SERVER_ACK:
                    logging.info("Received SERVER_ACK from server")
                elif msg_type == MessageType.SWITCH_CLIENT:
                    active_client = message.get("payload", {}).get("active_client")
                    logging.info(f"Server switched active client to: {active_client}")
                else:
                    logging.info(f"Received message from server: {msg_type}")
                    
            except Exception as e:
                if self.running:
                    logging.error(f"Error handling server message: {e}")
                break

    def _stream_video(self):
        """Captures and sends a real-time H.264 video stream."""
        capturer = ScreenCapturer() # Instantiate ScreenCapturer

        # Get the actual screen resolution from the capturer
        test_frame = capturer.capture_frame()
        if test_frame is None:
            logging.error("Failed to capture initial test frame")
            return
            
        actual_height, actual_width = test_frame.shape[:2]
        logging.info(f"Actual screen resolution: {actual_width}x{actual_height}")
        
        # Use actual screen resolution or scale proportionally
        width, height = actual_width, actual_height
        
        # If screen is too large, scale it down while maintaining aspect ratio
        max_dimension = 1920
        if width > max_dimension or height > max_dimension:
            scale_factor = min(max_dimension / width, max_dimension / height)
            width = int(width * scale_factor)
            height = int(height * scale_factor)
            logging.info(f"Scaled resolution: {width}x{height}")
        
        fps = 30

        stream = None
        try:
            # Create a single persistent stream for encoding
            container = av.open('dummy', mode='w', format='h264')
            stream = container.add_stream('h264', rate=fps)
            stream.width = width
            stream.height = height
            stream.pix_fmt = 'yuv420p'
            stream.options = {
                'crf': '23',
                'preset': 'ultrafast',
                'tune': 'zerolatency',  # Better for real-time streaming
                'keyint': '30',  # Force keyframes every 30 frames
            }
            
            logging.info("Successfully initialized real-time H.264 encoder with packet streaming.")
            
            frame_count = 0
            while self.running:
                frame_start_time = time.monotonic()
                try:
                    img = capturer.capture_frame() # Get frame from ScreenCapturer
                    if img is None:
                        logging.warning("No frame captured. Skipping.")
                        time.sleep(0.01) # Small sleep to prevent busy loop
                        continue

                    # Screen capturer now returns RGB directly, no conversion needed
                    # Resize the captured frame if needed
                    if (img.shape[1], img.shape[0]) != (width, height):
                        resized_frame = cv2.resize(img, (width, height))
                    else:
                        resized_frame = img

                    # Convert to PyAV frame (format='rgb24' for RGB)
                    av_frame = av.VideoFrame.from_ndarray(resized_frame, format='rgb24')
                    
                    # Force keyframe every 30 frames
                    if frame_count % 30 == 0:
                        av_frame.pict_type = av.video.frame.PictureType.I
                    
                    # Encode the frame and gather all packets into a single buffer
                    encoded_packets = stream.encode(av_frame)
                    frame_buffer = b"".join(bytes(p) for p in encoded_packets)
                    
                    if frame_buffer:
                        # Prepend the frame size as a 4-byte integer (big-endian)
                        frame_size = len(frame_buffer)
                        try:
                            self.video_socket.sendall(frame_size.to_bytes(4, 'big'))
                            self.video_socket.sendall(frame_buffer)
                            logging.info(f"Encoded and sent frame {frame_count} ({frame_size} bytes).")
                        except (ConnectionResetError, BrokenPipeError):
                            logging.warning("Video connection to server was lost while sending. Stopping stream.")
                            break
                    else:
                        logging.warning(f"No packets encoded for frame {frame_count}.")
                    
                    frame_count += 1

                    # Calculate actual FPS and adjust sleep for smoother streaming
                    elapsed_time = time.monotonic() - frame_start_time
                    time_to_sleep = (1 / fps) - elapsed_time
                    if time_to_sleep > 0:
                        time.sleep(time_to_sleep)

                except (ConnectionResetError, BrokenPipeError):
                    logging.warning("Video connection to server was lost. Stopping stream.")
                    break
                except Exception as e:
                    logging.error(f"Video capture/encoding error: {e}", exc_info=True) # Log full traceback
                    time.sleep(0.1) # Small delay to prevent rapid error looping
        
        except Exception as e:
            logging.error(f"FATAL: Could not initialize H.264 stream: {e}", exc_info=True)
        
        finally:
            if stream:
                try:
                    # Flush any remaining packets
                    flushed_packets = 0
                    for packet in stream.encode():
                        packet_bytes = bytes(packet)
                        self.video_socket.sendall(packet_bytes)
                        flushed_packets += 1
                    if flushed_packets > 0:
                        logging.info(f"Flushed {flushed_packets} remaining H.264 packets.")
                    logging.info("H.264 stream encoder closed.")
                except Exception as e:
                    logging.error(f"Error while closing H.264 stream: {e}")
            logging.info("Video streaming thread stopped.")

    def _send_video_data(self, video_data, server_ip, frame_id):
        """DEPRECATED: This method is no longer used in the new streaming architecture."""
        pass

    def _stream_video_jpeg(self):
        """Fallback JPEG streaming if H.264 fails."""
        sct = mss()
        if platform.system() == "Windows":
            monitor = sct.monitors[1]
        else:
            monitor = sct.monitors[1]
            
        server_ip = self._get_server_ip()
        while self.running:
            try:
                img = sct.grab(monitor)
                frame = np.array(img)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                frame = cv2.resize(frame, (1280, 720)) 
                
                # Encode with higher quality
                _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                if buffer is None: continue
                
                # Send frame in chunks with metadata
                chunk_size = 64000
                total_chunks = (len(buffer) + chunk_size - 1) // chunk_size
                frame_id = int(time.time() * 1000) % 100000
                
                for i in range(0, len(buffer), chunk_size):
                    chunk_data = buffer[i:i+chunk_size]
                    chunk_num = i // chunk_size + 1
                    
                    # Create chunk with metadata: frame_id(4) + chunk_num(2) + total_chunks(2) + is_video(1) + data
                    chunk_header = (frame_id.to_bytes(4, 'big') + 
                                  chunk_num.to_bytes(2, 'big') + 
                                  total_chunks.to_bytes(2, 'big') + 
                                  b'\x00')  # JPEG flag
                    chunk_with_header = chunk_header + chunk_data.tobytes()
                    
                    self.video_socket.sendto(chunk_with_header, (server_ip, self.video_port))

                time.sleep(1/30)
            except Exception as e:
                logging.error(f"JPEG streaming error: {e}")
                if not self.running:
                    break
                time.sleep(1)

    def _start_listeners(self):
        """Starts mouse and keyboard listeners."""
        self.mouse_listener = mouse.Listener(
            on_move=self.on_move,
            on_click=self.on_click,
            on_scroll=self.on_scroll)
        
        self.keyboard_listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release)

        self.mouse_listener.start()
        self.keyboard_listener.start()
        logging.info("Started keyboard and mouse listeners.")

    def on_move(self, x, y):
        if self.control_socket:
            payload = {'type': 'mouse_move', 'x': x, 'y': y}
            try:
                self.control_socket.send(create_message(MessageType.MOUSE_EVENT, payload))
            except:
                pass

    def on_click(self, x, y, button, pressed):
        if self.control_socket:
            payload = {'type': 'mouse_click', 'x': x, 'y': y, 'button': str(button), 'pressed': pressed}
            try:
                self.control_socket.send(create_message(MessageType.MOUSE_EVENT, payload))
            except:
                pass

    def on_scroll(self, x, y, dx, dy):
        if self.control_socket:
            payload = {'type': 'mouse_scroll', 'x': x, 'y': y, 'dx': dx, 'dy': dy}
            try:
                self.control_socket.send(create_message(MessageType.MOUSE_EVENT, payload))
            except:
                pass

    def on_press(self, key):
        if self.control_socket:
            try:
                payload = {'type': 'key_press', 'key': key.char}
            except AttributeError:
                payload = {'type': 'key_press', 'key': str(key)}
            try:
                self.control_socket.send(create_message(MessageType.KEY_EVENT, payload))
            except:
                pass

    def on_release(self, key):
        if self.control_socket:
            try:
                payload = {'type': 'key_release', 'key': key.char}
            except AttributeError:
                payload = {'type': 'key_release', 'key': str(key)}
            try:
                self.control_socket.send(create_message(MessageType.KEY_EVENT, payload))
            except:
                pass
        if key == keyboard.Key.esc:
            # Stop listener
            return False

def main():
    client = SourceAgentClient()
    try:
        client.start()
        while client.running:
            time.sleep(1) # Keep main thread alive
    except KeyboardInterrupt:
        print("Shutting down client...")
    finally:
        client.stop()

if __name__ == "__main__":
    main()