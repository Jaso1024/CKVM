import unittest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from source_agent.screen_capture import ScreenCapturer


class TestScreenCapturer(unittest.TestCase):
    
    @patch('source_agent.screen_capture.mss.mss')
    def setUp(self, mock_mss):
        self.mock_sct = Mock()
        mock_mss.return_value = self.mock_sct
        
        # Mock monitor configuration
        self.mock_sct.monitors = [
            {'top': 0, 'left': 0, 'width': 1920, 'height': 1080},  # All monitors combined
            {'top': 0, 'left': 0, 'width': 1920, 'height': 1080, 'id': 1}  # Primary monitor
        ]
        
        self.capturer = ScreenCapturer()
    
    def test_init_with_multiple_monitors(self):
        """Test that the capturer correctly selects the primary monitor when multiple exist."""
        expected_area = {
            "top": 0,
            "left": 0, 
            "width": 1920,
            "height": 1080,
            "mon": 1
        }
        self.assertEqual(self.capturer.capture_area, expected_area)
    
    @patch('source_agent.screen_capture.mss.mss')
    def test_init_with_single_monitor(self, mock_mss):
        """Test fallback to first monitor when only one exists."""
        mock_sct = Mock()
        mock_mss.return_value = mock_sct
        mock_sct.monitors = [{'top': 0, 'left': 0, 'width': 1920, 'height': 1080}]
        
        capturer = ScreenCapturer()
        expected_area = {
            "top": 0,
            "left": 0,
            "width": 1920, 
            "height": 1080
        }
        self.assertEqual(capturer.capture_area, expected_area)
    
    def test_capture_frame_success(self):
        """Test successful frame capture and color conversion."""
        # Mock BGRA image data (B=100, G=150, R=200, A=255)
        mock_bgra_data = np.full((1080, 1920, 4), [100, 150, 200, 255], dtype=np.uint8)
        mock_sct_img = Mock()
        mock_sct_img.__array__ = Mock(return_value=mock_bgra_data)
        
        self.mock_sct.grab.return_value = mock_sct_img
        
        result = self.capturer.capture_frame()
        
        # Should convert BGRA to RGB: [100,150,200,255] -> [200,150,100]
        expected_rgb = np.full((1080, 1920, 3), [200, 150, 100], dtype=np.uint8)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.shape, (1080, 1920, 3))
        self.assertTrue(np.array_equal(result, expected_rgb))
    
    def test_capture_frame_screenshot_error(self):
        """Test handling of screenshot errors."""
        from mss.exception import ScreenShotError
        self.mock_sct.grab.side_effect = ScreenShotError("Test error")
        
        with patch('builtins.print') as mock_print:
            result = self.capturer.capture_frame()
            
        self.assertIsNone(result)
        mock_print.assert_called_with("Screen capture error: Test error")
    
    def test_capture_frame_generic_error(self):
        """Test handling of generic errors."""
        self.mock_sct.grab.side_effect = Exception("Generic error")
        
        with patch('builtins.print') as mock_print:
            result = self.capturer.capture_frame()
            
        self.assertIsNone(result)
        mock_print.assert_called_with("An unexpected error occurred during screen capture: Generic error")
    
    def test_color_channel_conversion(self):
        """Test that BGRA is correctly converted to RGB."""
        # Create test data where each pixel has distinct BGRA values
        test_data = np.array([
            [[0, 64, 128, 255], [32, 96, 160, 255]],  # Row 1: 2 pixels
            [[16, 80, 144, 255], [48, 112, 176, 255]]  # Row 2: 2 pixels
        ], dtype=np.uint8)
        
        mock_sct_img = Mock()
        mock_sct_img.__array__ = Mock(return_value=test_data)
        self.mock_sct.grab.return_value = mock_sct_img
        
        result = self.capturer.capture_frame()
        
        # Expected RGB (swap B and R channels, drop A)
        expected = np.array([
            [[128, 64, 0], [160, 96, 32]],    # B->R, G->G, R->B
            [[144, 80, 16], [176, 112, 48]]
        ], dtype=np.uint8)
        
        self.assertTrue(np.array_equal(result, expected))


if __name__ == '__main__':
    unittest.main()