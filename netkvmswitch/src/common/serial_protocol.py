import struct
import json

def send_framed(serial_conn, message_data):
    """
    Sends a framed message over a serial connection.
    Each message is prefixed with a 4-byte length (big-endian).
    """
    try:
        encoded_message = json.dumps(message_data).encode('utf-8')
        frame = struct.pack('>I', len(encoded_message)) + encoded_message
        serial_conn.write(frame)
        return True
    except Exception as e:
        print(f"Error sending framed message: {e}")
        return False

def receive_framed(serial_conn):
    """
    Receives a framed message from a serial connection.
    Returns the parsed message data (dict) or None on error.
    """
    try:
        # Read the 4-byte length prefix
        len_prefix = serial_conn.read(4)
        if not len_prefix or len(len_prefix) < 4:
            return None # Connection closed or invalid data
            
        msg_len = struct.unpack('>I', len_prefix)[0]
        
        # Read the full message
        encoded_message = serial_conn.read(msg_len)
        if not encoded_message or len(encoded_message) < msg_len:
            return None # Connection closed prematurely

        return json.loads(encoded_message.decode('utf-8'))
    except (struct.error, json.JSONDecodeError) as e:
        print(f"Error decoding message: {e}")
        # Potentially clear the buffer or handle the error more gracefully
        return None
    except Exception as e:
        print(f"Error receiving framed message: {e}")
        return None 