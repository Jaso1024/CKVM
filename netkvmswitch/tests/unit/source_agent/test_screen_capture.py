import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from source_agent.screen_capture import ScreenCapturer

@patch('source_agent.screen_capture.mss.mss')
def test_screen_capturer_initialization(mock_mss):
    mock_sct_instance = mock_mss.return_value
    mock_sct_instance.monitors = [{'top': 0, 'left': 0, 'width': 1920, 'height': 1080, 'id': 1}, {'top': 0, 'left': 0, 'width': 1920, 'height': 1080, 'id': 1}]
    
    capturer = ScreenCapturer()
    assert capturer.sct is mock_sct_instance
    assert capturer.monitor == {'top': 0, 'left': 0, 'width': 1920, 'height': 1080, 'id': 1}
    assert capturer.capture_area == {
        "top": 0,
        "left": 0,
        "width": 1920,
        "height": 1080,
        "mon": 1,
    }

@patch('source_agent.screen_capture.mss.mss')
def test_capture_frame_returns_numpy_array(mock_mss):
    mock_sct_instance = mock_mss.return_value
    mock_sct_instance.monitors = [{'top': 0, 'left': 0, 'width': 1920, 'height': 1080, 'id': 1}, {'top': 0, 'left': 0, 'width': 1920, 'height': 1080, 'id': 1}]

    # Simulate a captured image (BGRA format)
    mock_sct_instance.grab.return_value = MagicMock()
    mock_sct_instance.grab.return_value.rgb = b'\x00\x00\x00\xff' * (10 * 10) # 10x10 black image with alpha
    mock_sct_instance.grab.return_value.width = 10
    mock_sct_instance.grab.return_value.height = 10
    mock_sct_instance.grab.return_value.size = 10 * 10 * 4

    # Patch numpy.array to return a mock array with expected shape
    with patch('source_agent.screen_capture.np.array') as mock_np_array:
        mock_np_array.return_value = np.zeros((10, 10, 4), dtype=np.uint8) # Simulate BGRA
        capturer = ScreenCapturer()
        frame = capturer.capture_frame()

        assert frame is not None
        assert isinstance(frame, np.ndarray)
        # Expecting BGR format after dropping alpha
        assert frame.shape == (10, 10, 3)
        mock_sct_instance.grab.assert_called_once()

@patch('source_agent.screen_capture.mss.mss')
def test_capture_frame_handles_error(mock_mss):
    mock_sct_instance = mock_mss.return_value
    mock_sct_instance.monitors = [{'top': 0, 'left': 0, 'width': 1920, 'height': 1080, 'id': 1}, {'top': 0, 'left': 0, 'width': 1920, 'height': 1080, 'id': 1}]
    mock_sct_instance.grab.side_effect = mss.exception.ScreenShotError("Test Error")

    capturer = ScreenCapturer()
    frame = capturer.capture_frame()

    assert frame is None
    mock_sct_instance.grab.assert_called_once()