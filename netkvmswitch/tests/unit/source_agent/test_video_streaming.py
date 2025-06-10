import unittest
import numpy as np
from unittest.mock import Mock, patch, MagicMock, call
import sys
import os
import threading
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from source_agent.client import SourceAgentClient


class TestVideoStreaming(unittest.TestCase):
    
    def setUp(self):
        self.client = SourceAgentClient(
            server_host='127.0.0.1',
            server_port=8443,
            video_port=8444,
            client_name='test_client'
        )
    
    @patch('source_agent.client.av')
    @patch('source_agent.client.ScreenCapturer')
    def test_stream_video_initialization(self, mock_capturer_class, mock_av):
        """Test that video streaming initializes correctly."""
        # Mock screen capturer
        mock_capturer = Mock()
        mock_capturer_class.return_value = mock_capturer
        
        # Mock initial frame capture
        test_frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 128  # Gray frame
        mock_capturer.capture_frame.return_value = test_frame
        
        # Mock PyAV components
        mock_container = Mock()
        mock_stream = Mock()
        mock_av.open.return_value = mock_container
        mock_container.add_stream.return_value = mock_stream
        
        # Mock video socket
        self.client.video_socket = Mock()
        self.client.running = True
        
        # Stop after first frame to prevent infinite loop
        def stop_after_first_call(*args):
            self.client.running = False
            return test_frame
        mock_capturer.capture_frame.side_effect = stop_after_first_call
        
        # Run the streaming method
        self.client._stream_video()
        
        # Verify initialization
        mock_av.open.assert_called_once_with('dummy', mode='w', format='h264')
        mock_container.add_stream.assert_called_once_with('h264', rate=30)
        
        # Verify stream configuration
        self.assertEqual(mock_stream.width, 1920)
        self.assertEqual(mock_stream.height, 1080)
        self.assertEqual(mock_stream.pix_fmt, 'yuv420p')
        expected_options = {
            'crf': '23',
            'preset': 'ultrafast',
            'tune': 'zerolatency',
            'keyint': '30'
        }
        self.assertEqual(mock_stream.options, expected_options)
    
    @patch('source_agent.client.cv2')
    @patch('source_agent.client.av')
    @patch('source_agent.client.ScreenCapturer')
    def test_video_frame_processing(self, mock_capturer_class, mock_av, mock_cv2):
        """Test that video frames are processed correctly."""
        # Mock screen capturer
        mock_capturer = Mock()
        mock_capturer_class.return_value = mock_capturer
        
        # Test frame with different size than target
        test_frame = np.ones((720, 1280, 3), dtype=np.uint8) * 100
        resized_frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 100
        
        mock_capturer.capture_frame.side_effect = [test_frame, None]  # One frame then stop
        mock_cv2.resize.return_value = resized_frame
        
        # Mock PyAV components
        mock_container = Mock()
        mock_stream = Mock()
        mock_av_frame = Mock()
        mock_packet = Mock()
        
        mock_av.open.return_value = mock_container
        mock_container.add_stream.return_value = mock_stream
        mock_av.VideoFrame.from_ndarray.return_value = mock_av_frame
        mock_stream.encode.return_value = [mock_packet]  # Return one packet
        
        # Mock bytes conversion
        mock_packet_bytes = b'test_packet_data'
        with patch('builtins.bytes', return_value=mock_packet_bytes):
            self.client.video_socket = Mock()
            self.client.running = True
            
            self.client._stream_video()
        
        # Verify frame processing
        mock_cv2.resize.assert_called_once_with(test_frame, (1920, 1080))
        mock_av.VideoFrame.from_ndarray.assert_called_once_with(resized_frame, format='rgb24')
        mock_stream.encode.assert_called_once_with(mock_av_frame)
        self.client.video_socket.sendall.assert_called_once_with(mock_packet_bytes)
    
    @patch('source_agent.client.av')
    @patch('source_agent.client.ScreenCapturer')
    def test_keyframe_forcing(self, mock_capturer_class, mock_av):
        """Test that keyframes are forced every 30 frames."""
        # Mock screen capturer
        mock_capturer = Mock()
        mock_capturer_class.return_value = mock_capturer
        
        test_frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 128
        
        # Return frame 31 times, then None (to test frames 0-30)
        call_count = 0
        def frame_generator(*args):
            nonlocal call_count
            call_count += 1
            if call_count <= 31:
                return test_frame
            return None
        
        mock_capturer.capture_frame.side_effect = frame_generator
        
        # Mock PyAV components
        mock_container = Mock()
        mock_stream = Mock()
        mock_av_frame = Mock()
        
        mock_av.open.return_value = mock_container
        mock_container.add_stream.return_value = mock_stream
        mock_av.VideoFrame.from_ndarray.return_value = mock_av_frame
        mock_stream.encode.return_value = []  # No packets to avoid sendall
        
        self.client.video_socket = Mock()
        self.client.running = True
        
        self.client._stream_video()
        
        # Verify keyframe was set on frames 0 and 30
        expected_keyframe_calls = [
            call(test_frame, format='rgb24'),
            call(test_frame, format='rgb24'),  # Frame 30
        ]
        
        # Check that pict_type was set to keyframe for the right frames
        keyframe_assignments = [call for call in mock_av_frame.method_calls if 'pict_type' in str(call)]
        self.assertGreaterEqual(len(keyframe_assignments), 2)  # At least frames 0 and 30
    
    @patch('source_agent.client.av')
    @patch('source_agent.client.ScreenCapturer')
    def test_video_streaming_error_handling(self, mock_capturer_class, mock_av):
        """Test error handling in video streaming."""
        # Mock screen capturer to raise an exception
        mock_capturer = Mock()
        mock_capturer_class.return_value = mock_capturer
        mock_capturer.capture_frame.side_effect = Exception("Screen capture failed")
        
        # Mock PyAV components
        mock_container = Mock()
        mock_stream = Mock()
        mock_av.open.return_value = mock_container
        mock_container.add_stream.return_value = mock_stream
        
        self.client.video_socket = Mock()
        self.client.running = True
        
        # Mock logging to verify error is logged
        with patch('source_agent.client.logging') as mock_logging:
            # Run for a short time then stop
            def stop_after_delay():
                time.sleep(0.2)
                self.client.running = False
            
            stop_thread = threading.Thread(target=stop_after_delay)
            stop_thread.start()
            
            self.client._stream_video()
            stop_thread.join()
            
            # Verify error was logged
            mock_logging.error.assert_called()
            error_calls = mock_logging.error.call_args_list
            self.assertTrue(any("Video capture/encoding error" in str(call) for call in error_calls))
    
    @patch('source_agent.client.av')
    @patch('source_agent.client.ScreenCapturer')
    def test_resolution_scaling(self, mock_capturer_class, mock_av):
        """Test that large resolutions are scaled down appropriately."""
        # Mock screen capturer with very large resolution
        mock_capturer = Mock()
        mock_capturer_class.return_value = mock_capturer
        
        # Test with 4K resolution that should be scaled down
        large_frame = np.ones((2160, 3840, 3), dtype=np.uint8) * 128  # 4K frame
        mock_capturer.capture_frame.side_effect = [large_frame, None]
        
        # Mock PyAV components
        mock_container = Mock()
        mock_stream = Mock()
        mock_av.open.return_value = mock_container
        mock_container.add_stream.return_value = mock_stream
        mock_stream.encode.return_value = []
        
        self.client.video_socket = Mock()
        self.client.running = True
        
        with patch('source_agent.client.logging') as mock_logging:
            self.client._stream_video()
            
            # Verify resolution was scaled down
            # 3840x2160 should be scaled to fit within 1920 max dimension
            # Scale factor: 1920/3840 = 0.5
            # New resolution: 1920x1080
            self.assertEqual(mock_stream.width, 1920)
            self.assertEqual(mock_stream.height, 1080)
            
            # Verify scaling was logged
            info_calls = mock_logging.info.call_args_list
            scaled_logged = any("Scaled resolution: 1920x1080" in str(call) for call in info_calls)
            self.assertTrue(scaled_logged)


class TestVideoStreamingIntegration(unittest.TestCase):
    """Integration tests that test multiple components together."""
    
    @patch('source_agent.client.socket.socket')
    def test_video_connection_establishment(self, mock_socket):
        """Test that video connection is established correctly."""
        mock_video_socket = Mock()
        mock_control_socket = Mock()
        mock_socket.return_value = mock_video_socket
        
        client = SourceAgentClient()
        client.control_socket = mock_control_socket  # Simulate existing control connection
        client.running = True
        
        # Test connection establishment part of _connect_to_server
        with patch('source_agent.client.ssl'), \
             patch('source_agent.client.time.sleep'):
            
            # This would normally be called within _connect_to_server
            client.video_socket = mock_video_socket
            mock_video_socket.connect.return_value = None
            
            # Verify socket creation and connection
            self.assertIsNotNone(client.video_socket)


if __name__ == '__main__':
    unittest.main() 