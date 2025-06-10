import pytest
from common.protocol import create_message, parse_message, MessageType

def test_create_and_parse_message():
    # Test KEY_EVENT
    key_payload = {"event_type": "press", "key": "a"}
    key_message = create_message(MessageType.KEY_EVENT, key_payload)
    parsed_key_message = parse_message(key_message)
    assert parsed_key_message["type"] == MessageType.KEY_EVENT
    assert parsed_key_message["payload"] == key_payload

    # Test MOUSE_EVENT
    mouse_payload = {"event_type": "click", "x": 100, "y": 200, "button": "Button.left", "pressed": True}
    mouse_message = create_message(MessageType.MOUSE_EVENT, mouse_payload)
    parsed_mouse_message = parse_message(mouse_message)
    assert parsed_mouse_message["type"] == MessageType.MOUSE_EVENT
    assert parsed_mouse_message["payload"] == mouse_payload

    # Test CLIENT_HELLO
    hello_payload = {"name": "test_client", "version": "1.0"}
    hello_message = create_message(MessageType.CLIENT_HELLO, hello_payload)
    parsed_hello_message = parse_message(hello_message)
    assert parsed_hello_message["type"] == MessageType.CLIENT_HELLO
    assert parsed_hello_message["payload"] == hello_payload

    # Test SERVER_ACK
    ack_payload = {"status": "connected", "client_id": "abc-123"}
    ack_message = create_message(MessageType.SERVER_ACK, ack_payload)
    parsed_ack_message = parse_message(ack_message)
    assert parsed_ack_message["type"] == MessageType.SERVER_ACK
    assert parsed_ack_message["payload"] == ack_payload

    # Test SWITCH_CLIENT
    switch_payload = {"active_client": "192.168.1.100"}
    switch_message = create_message(MessageType.SWITCH_CLIENT, switch_payload)
    parsed_switch_message = parse_message(switch_message)
    assert parsed_switch_message["type"] == MessageType.SWITCH_CLIENT
    assert parsed_switch_message["payload"] == switch_payload

    # Test with empty payload
    empty_message = create_message("TEST_EMPTY", {})
    parsed_empty_message = parse_message(empty_message)
    assert parsed_empty_message["type"] == "TEST_EMPTY"
    assert parsed_empty_message["payload"] == {}

    # Test with complex payload
    complex_payload = {"data": [1, 2, {"key": "value"}], "status": True}
    complex_message = create_message("TEST_COMPLEX", complex_payload)
    parsed_complex_message = parse_message(complex_message)
    assert parsed_complex_message["type"] == "TEST_COMPLEX"
    assert parsed_complex_message["payload"] == complex_payload