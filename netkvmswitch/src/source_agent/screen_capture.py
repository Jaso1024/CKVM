# Screen capture and video streaming

import mss
import numpy as np
import time
import cv2

class ScreenCapturer:
    def __init__(self):
        self.sct = mss.mss()
        # Capture the primary monitor (index 1 for individual monitors, 0 for all combined)
        # On some systems, monitors[0] might be the combined virtual screen, and actual monitors start from monitors[1]
        # Let's try to iterate and find a suitable monitor or default to the first one that has 'id'
        # Or, more simply, use the first actual monitor if it exists.
        if len(self.sct.monitors) > 1:
            self.monitor = self.sct.monitors[1] # Use the first actual monitor
        else:
            # Fallback if only one monitor entry (might be combined virtual screen)
            self.monitor = self.sct.monitors[0]

        self.capture_area = {
            "top": self.monitor["top"],
            "left": self.monitor["left"],
            "width": self.monitor["width"],
            "height": self.monitor["height"],
        }
        # The 'mon' key with 'id' is not always present or necessary for mss.grab
        # when top, left, width, and height are provided.
        if "id" in self.monitor:
            self.capture_area["mon"] = self.monitor["id"]

    def capture_frame(self):
        """Captures a single frame from the screen."""
        try:
            sct_img = self.sct.grab(self.capture_area)
            # Convert to a numpy array
            img = np.array(sct_img)
            # MSS captures in BGRA, convert to RGB for the encoder
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
            return img
        except mss.exception.ScreenShotError as e:
            print(f"Screen capture error: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during screen capture: {e}")
            return None

# Example usage (for testing)
if __name__ == "__main__":
    capturer = ScreenCapturer()
    print("Starting screen capture... Press Ctrl+C to stop.")
    try:
        while True:
            frame = capturer.capture_frame()
            if frame is not None:
                print(f"Captured frame with shape: {frame.shape}")
                # You would typically process or send the frame here
            time.sleep(0.1) # Capture at 10 FPS
    except KeyboardInterrupt:
        print("Screen capture stopped.")
