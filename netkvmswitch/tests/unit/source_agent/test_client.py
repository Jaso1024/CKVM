import pytest
import socket
import threading
import time
from unittest.mock import MagicMock, patch

from source_agent.client import SourceAgentClient
from common.protocol import create_message, parse_message, MessageType

@pytest.fixture
def client():
    c = SourceAgentClient(server_host='127.0.0.1', server_port=12347) # Use a different port
    yield c
    c.stop()

@patch('source_agent.client.socket.socket')
def test_client_connects_and_sends_hello(mock_socket, client):
    mock_instance = mock_socket.return_value
    client.start()
    mock_instance.connect.assert_called_once_with(('127.0.0.1', 12347))
    mock_instance.sendall.assert_called_once()
    assert client.running is True

@patch('source_agent.client.KeyboardController')
@patch('source_agent.client.MouseController')
def test_client_injects_keyboard_event(mock_mouse_controller, mock_keyboard_controller, client):
    mock_keyboard_instance = mock_keyboard_controller.return_value

    # Simulate receiving a key press message
    key_payload = {"event_type": "press", "key": "a"}
    key_message = {"type": MessageType.KEY_EVENT, "payload": key_payload}
    client._handle_command(key_message)
    mock_keyboard_instance.press.assert_called_once_with('a')

    # Simulate receiving a key release message
    key_payload = {"event_type": "release", "key": "a"}
    key_message = {"type": MessageType.KEY_EVENT, "payload": key_payload}
    client._handle_command(key_message)
    mock_keyboard_instance.release.assert_called_once_with('a')

    # Simulate special key
    mock_keyboard_instance.reset_mock()
    key_payload = {"event_type": "press", "key": "Key.space"}
    key_message = {"type": MessageType.KEY_EVENT, "payload": key_payload}
    client._handle_command(key_message)
    mock_keyboard_instance.press.assert_called_once_with(client.keyboard_controller.Key.space)

@patch('source_agent.client.KeyboardController')
@patch('source_agent.client.MouseController')
def test_client_injects_mouse_event(mock_mouse_controller, mock_keyboard_controller, client):
    mock_mouse_instance = mock_mouse_controller.return_value

    # Simulate receiving a mouse click message (press)
    mouse_payload = {"event_type": "click", "x": 100, "y": 200, "button": "Button.left", "pressed": True}
    mouse_message = {"type": MessageType.MOUSE_EVENT, "payload": mouse_payload}
    client._handle_command(mouse_message)
    assert mock_mouse_instance.position == (100, 200)
    mock_mouse_instance.press.assert_called_once_with(client.mouse_controller.Button.left)

    # Simulate receiving a mouse click message (release)
    mock_mouse_instance.reset_mock()
    mouse_payload = {"event_type": "click", "x": 100, "y": 200, "button": "Button.left", "pressed": False}
    mouse_message = {"type": MessageType.MOUSE_EVENT, "payload": mouse_payload}
    client._handle_command(mouse_message)
    assert mock_mouse_instance.position == (100, 200)
    mock_mouse_instance.release.assert_called_once_with(client.mouse_controller.Button.left)

    # Simulate receiving a mouse scroll message
    mock_mouse_instance.reset_mock()
    mouse_payload = {"event_type": "scroll", "x": 0, "y": 0, "dx": 0, "dy": 1}
    mouse_message = {"type": MessageType.MOUSE_EVENT, "payload": mouse_payload}
    client._handle_command(mouse_message)
    mock_mouse_instance.scroll.assert_called_once_with(0, 1)

    # Simulate receiving a mouse move message
    mock_mouse_instance.reset_mock()
    mouse_payload = {"event_type": "move", "x": 500, "y": 500}
    mouse_message = {"type": MessageType.MOUSE_EVENT, "payload": mouse_payload}
    client._handle_command(mouse_message)
    assert mock_mouse_instance.position == (500, 500)

@patch('source_agent.client.socket.socket')
def test_client_stops_on_server_disconnect(mock_socket, client):
    mock_instance = mock_socket.return_value
    mock_instance.recv.return_value = b'' # Simulate server disconnect

    client.start()
    time.sleep(0.1) # Give thread time to run
    assert client.running is False
    mock_instance.close.assert_called_once()