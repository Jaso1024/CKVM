import time
import sys
import os
import cv2
import numpy as np
import serial
import serial.tools.list_ports
import threading
import base64
from pynput.keyboard import Controller as KeyboardController, Key
from pynput.mouse import Controller as MouseController, Button

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.config import config
from common.protocol import MessageType
from common.serial_protocol import send_framed, receive_framed
from source_agent.screen_capture import ScreenCapturer

class USBSourceAgent:
    def __init__(self, port=None):
        self.port = port
        self.conn = None
        self.running = False
        self.keyboard_controller = KeyboardController()
        self.mouse_controller = MouseController()

    def start(self):
        """Find and connect to the server over a serial port."""
        if self.port:
            ports_to_try = [self.port]
        else:
            print("[USB Client] No port specified, scanning for server...")
            ports_to_try = [p.device for p in serial.tools.list_ports.comports()]
        
        for port in ports_to_try:
            try:
                print(f"[USB Client] Trying port {port}...")
                conn = serial.Serial(port, baudrate=115200, timeout=2)
                
                # Wait for server hello
                message = receive_framed(conn)
                if message and message.get("payload", {}).get("magic") == "NETKVM_SERVER_HELLO":
                    print(f"[USB Client] Server found on {port}. Sending client hello.")
                    client_hello = {
                        "type": "handshake",
                        "payload": {
                            "magic": "NETKVM_CLIENT_HELLO",
                            "name": config.client.client_name
                        }
                    }
                    if send_framed(conn, client_hello):
                        self.conn = conn
                        self.running = True
                        print("[USB Client] Connection successful!")
                        break # Exit loop once connected
                else:
                    conn.close()
            except serial.SerialException:
                continue # Try next port
        
        if self.running:
            threading.Thread(target=self._listen_for_commands, daemon=True).start()
            threading.Thread(target=self._stream_video, daemon=True).start()
        else:
            print("[USB Client] Could not find or connect to server.")

    def _listen_for_commands(self):
        """Listen for I/O commands from the server."""
        while self.running:
            try:
                message = receive_framed(self.conn)
                if message is None:
                    print("[USB Client] Server disconnected.")
                    break
                self._handle_command(message)
            except Exception as e:
                print(f"[USB Client] Error receiving command: {e}")
                break
        self.running = False
        
    def _stream_video(self):
        """Capture and stream video frames to the server."""
        capturer = ScreenCapturer()
        encode_param = [cv2.IMWRITE_JPEG_QUALITY, config.client.video_quality]
        fps_delay = 1.0 / config.client.fps

        while self.running:
            try:
                frame = capturer.capture_frame()
                if frame is not None:
                    target_width = config.client.video_width
                    aspect_ratio = frame.shape[1] / frame.shape[0]
                    target_height = int(target_width / aspect_ratio)
                    resized = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
                    
                    _, encoded_frame = cv2.imencode('.jpg', resized, encode_param)
                    frame_data = base64.b64encode(encoded_frame.tobytes()).decode('utf-8')
                    
                    video_message = {
                        "type": MessageType.VIDEO_FRAME,
                        "payload": {"frame": frame_data}
                    }
                    if not send_framed(self.conn, video_message):
                        print("[USB Client] Failed to send video frame.")
                        break # Stop streaming on error
                
                time.sleep(fps_delay)
            except Exception as e:
                print(f"[USB Client] Error streaming video: {e}")
                break
        self.running = False

    def _handle_command(self, message):
        msg_type = message.get("type")
        payload = message.get("payload")
        if msg_type == MessageType.KEY_EVENT:
            self._inject_key_event(payload)
        elif msg_type == MessageType.MOUSE_EVENT:
            self._inject_mouse_event(payload)

    def _inject_key_event(self, payload):
        # (This is identical to the TCP client's implementation)
        event_type = payload["event_type"]
        key_str = payload["key"]
        try:
            key = getattr(Key, key_str.split('.')[-1]) if key_str.startswith('Key.') else key_str
            if event_type == "press":
                self.keyboard_controller.press(key)
            elif event_type == "release":
                self.keyboard_controller.release(key)
        except Exception as e:
            print(f"Error injecting key event {key_str}: {e}")

    def _inject_mouse_event(self, payload):
        # (This is identical to the TCP client's implementation)
        event_type = payload["event_type"]
        if event_type == "click":
            button = getattr(Button, payload["button"].split('.')[-1])
            self.mouse_controller.position = (payload["x"], payload["y"])
            if payload["pressed"]:
                self.mouse_controller.press(button)
            else:
                self.mouse_controller.release(button)
        elif event_type == "scroll":
            self.mouse_controller.scroll(payload["dx"], payload["dy"])
        elif event_type == "move":
            self.mouse_controller.position = (payload["x"], payload["y"])

    def stop(self):
        self.running = False
        if self.conn and self.conn.is_open:
            self.conn.close()
        print("[USB Client] Stopped.")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="NetKVMSwitch USB Source Agent")
    parser.add_argument("--port", help="The serial port to connect to (e.g., COM3 or /dev/ttyACM0)")
    args = parser.parse_args()

    client = USBSourceAgent(port=args.port)
    try:
        client.start()
        while client.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[USB Client] Shutting down...")
    finally:
        client.stop()

if __name__ == "__main__":
    main() 