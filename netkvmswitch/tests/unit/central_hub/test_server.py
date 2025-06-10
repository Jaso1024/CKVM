import pytest
import socket
import threading
import time
from unittest.mock import MagicMock, patch

from central_hub.server import CentralHubServer
from common.protocol import create_message, MessageType

@pytest.fixture
def server():
    s = CentralHubServer(host='127.0.0.1', port=12346) # Use a different port for testing
    yield s
    s.stop()

@patch('central_hub.server.keyboard.Listener')
@patch('central_hub.server.mouse.Listener')
def test_server_starts_and_stops(mock_mouse_listener, mock_keyboard_listener, server):
    server.start()
    assert server.running is True
    mock_keyboard_listener.assert_called_once()
    mock_mouse_listener.assert_called_once()
    server.stop()
    assert server.running is False
    mock_keyboard_listener.return_value.stop.assert_called_once()
    mock_mouse_listener.return_value.stop.assert_called_once()

@patch('central_hub.server.keyboard.Listener')
@patch('central_hub.server.mouse.Listener')
def test_server_handles_new_client_connection(mock_mouse_listener, mock_keyboard_listener, server):
    server.start()
    time.sleep(0.1) # Give server a moment to start

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect(('127.0.0.1', 12346))
        client_socket.sendall(create_message(MessageType.CLIENT_HELLO, {"name": "test_client"}))

        # Wait for server to process connection and set active client
        time.sleep(0.1)

        assert len(server.clients) == 1
        assert server.active_client_address is not None

        # Check if server sent ACK
        ack_data = client_socket.recv(4096)
        assert ack_data is not None
        # Further parsing of ack_data can be done if needed

    finally:
        client_socket.close()

@patch('central_hub.server.keyboard.Listener')
@patch('central_hub.server.mouse.Listener')
def test_server_forwards_keyboard_event_to_active_client(mock_mouse_listener, mock_keyboard_listener, server):
    server.start()
    time.sleep(0.1)

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect(('127.0.0.1', 12346))
        client_socket.sendall(create_message(MessageType.CLIENT_HELLO, {"name": "test_client"}))
        time.sleep(0.1)

        # Simulate a key press on the server side
        mock_keyboard_listener.return_value.on_press = server._on_key_press
        mock_keyboard_listener.return_value.on_release = server._on_key_release

        # Manually call the internal method that pynput would call
        mock_key = MagicMock()
        mock_key.char = 'a'
        server._on_key_press(mock_key)

        # Check if the client received the key event
        received_data = client_socket.recv(4096)
        assert received_data is not None
        message = parse_message(received_data)
        assert message["type"] == MessageType.KEY_EVENT
        assert message["payload"]["event_type"] == "press"
        assert message["payload"]["key"] == "a"

    finally:
        client_socket.close()

@patch('central_hub.server.keyboard.Listener')
@patch('central_hub.server.mouse.Listener')
def test_server_forwards_mouse_event_to_active_client(mock_mouse_listener, mock_keyboard_listener, server):
    server.start()
    time.sleep(0.1)

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect(('127.0.0.1', 12346))
        client_socket.sendall(create_message(MessageType.CLIENT_HELLO, {"name": "test_client"}))
        time.sleep(0.1)

        # Simulate a mouse click on the server side
        mock_mouse_listener.return_value.on_click = server._on_mouse_click

        # Manually call the internal method that pynput would call
        mock_button = MagicMock()
        mock_button.__str__.return_value = 'Button.left'
        server._on_mouse_click(100, 200, mock_button, True)

        # Check if the client received the mouse event
        received_data = client_socket.recv(4096)
        assert received_data is not None
        message = parse_message(received_data)
        assert message["type"] == MessageType.MOUSE_EVENT
        assert message["payload"]["event_type"] == "click"
        assert message["payload"]["x"] == 100
        assert message["payload"]["y"] == 200
        assert message["payload"]["button"] == "Button.left"
        assert message["payload"]["pressed"] is True

    finally:
        client_socket.close()

@patch('central_hub.server.keyboard.Listener')
@patch('central_hub.server.mouse.Listener')
def test_server_rejects_input_if_no_active_client(mock_mouse_listener, mock_keyboard_listener, server):
    server.start()
    time.sleep(0.1)

    # Ensure no active client initially
    server.active_client_address = None

    # Simulate a key press
    mock_keyboard_listener.return_value.on_press = server._on_key_press
    mock_key = MagicMock()
    mock_key.char = 'b'
    server._on_key_press(mock_key)

    # No client connected, so no message should be sent. This test primarily checks no errors occur.
    # A more robust test would involve mocking the client socket's sendall method and asserting it's not called.
    assert server.active_client_address is None # Still no active client

@patch('central_hub.server.keyboard.Listener')
@patch('central_hub.server.mouse.Listener')
def test_server_removes_client_on_disconnect(mock_mouse_listener, mock_keyboard_listener, server):
    server.start()
    time.sleep(0.1)

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect(('127.0.0.1', 12346))
        client_socket.sendall(create_message(MessageType.CLIENT_HELLO, {"name": "test_client"}))
        time.sleep(0.1)
        assert len(server.clients) == 1

    finally:
        client_socket.close()
        time.sleep(0.1) # Give server time to detect disconnect
        assert len(server.clients) == 0
        assert server.active_client_address is None