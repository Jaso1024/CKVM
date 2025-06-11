# Message definitions, serialization
import json

class MessageType:
    KEY_EVENT = "key_event"
    MOUSE_EVENT = "mouse_event"
    CLIENT_HELLO = "client_hello"
    SERVER_ACK = "server_ack"
    SWITCH_CLIENT = "switch_client"
    STREAM_STATUS = "stream_status"
    CLIPBOARD_EVENT = "clipboard_event"
    VIDEO_FRAME = "video_frame"
    SHUTDOWN = "shutdown"

def create_message(msg_type, payload):
    return json.dumps({"type": msg_type, "payload": payload}).encode('utf-8')

def parse_message(data):
    return json.loads(data.decode('utf-8'))
