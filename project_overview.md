# NetKVMSwitch: Comprehensive Project Overview

## 1. High-Level Summary

NetKVMSwitch is a software-based KVM (Keyboard, Video, Mouse) solution that allows a central computer (the "Hub") to view and control multiple source computers (the "Agents") over a network. It features a high-performance, multi-threaded architecture with a native C++ backend for video processing and a Streamlit web UI for control.

The project is composed of three main parts:
1.  **Central Hub (Server)**: A Python application that manages client connections, captures local keyboard/mouse input, and forwards it to the active client. It also receives video streams from all clients and forwards the active stream to the UI.
2.  **Source Agent (Client)**: A Python application that runs on the source machines. It captures the screen, streams it to the Hub, and is intended to receive and inject keyboard/mouse events from the Hub.
3.  **Streamlit UI**: A web-based interface for managing the system, selecting the active client, and viewing the video stream.

A key feature is the **adaptive source agent**, which automatically uses a high-performance C++ backend for screen capture and video encoding if available, falling back to a pure Python implementation if not.

---

## 2. Project Structure and File Breakdown

This section details the purpose of each file and directory in the `netkvmswitch` subfolder.

### `/` (Root)

*   `config.json`: Default configuration for the server, client, security, and UI.
*   `generate_certs.py`: Script to generate self-signed TLS certificates for secure communication.
*   `requirements.txt`: A list of all Python dependencies for the project.
*   `setup.py`: The build script for the native C++ extension. It uses `pybind11` to compile the C++ code into a Python module (`kvmstream_native`). It handles platform-specific build flags and linking against FFmpeg.
*   `run_ui.py`, `run_server.py`, `run_client.py`: Simple wrapper scripts to run the UI, server, and client respectively.
*   `*.dll`: FFmpeg DLLs required for the native C++ module on Windows.

### `src/common/`

This directory contains code shared between the Hub and the Agent.

*   `config.py`: Defines dataclasses for configuration (`ServerConfig`, `ClientConfig`, etc.). It loads settings from `config.json` and can override them with environment variables.
*   `protocol.py`: Defines the simple JSON-based communication protocol, including message types (`KEY_EVENT`, `MOUSE_EVENT`, etc.) and functions to create and parse messages.
*   `serial_protocol.py`: Implements a framed messaging protocol (length-prefixing) for use over serial (USB) connections.
*   `utils.py`: Currently empty, intended for shared utility functions.

### `src/central_hub/`

This directory contains all the server-side logic.

*   `hub_runner.py`: A script to run the `CentralHubServer` in a separate process, used by the UI to launch the server in the background.
*   `server.py`: The core of the server application.
    *   Manages multiple TCP sockets for client control, client video, UI control, and UI video.
    *   Handles TLS for secure client connections.
    *   Uses `pynput` to capture local keyboard and mouse events on the Hub machine.
    *   Forwards captured input events to the currently active client.
    *   Receives framed H.264 video packets from the active client and forwards them to the UI.
    *   Includes a listener to detect and handle clients connecting via USB/serial.
*   `state_manager.py`: A thread-safe class that manages the server's state, including the list of connected clients, the currently active client, and the latest video frames.

### `src/source_agent/`

This directory contains all the client-side logic.

*   `agent_runner.py`: The main entry point for the source agent. It instantiates and runs the `AdaptiveSourceAgent`.
*   `native_client.py`: Implements the `AdaptiveSourceAgent`.
    *   It first tries to load the C++ `kvmstream_native` module.
    *   If successful, it uses the high-performance `NativeSourceAgent` which controls the C++ backend.
    *   If the native module is not available, it falls back to the pure Python `SourceAgentClient`.
*   `client.py`: The pure Python implementation of the source agent.
    *   Establishes a TLS control connection and a TCP video connection to the Hub.
    *   Implements a highly optimized, multi-threaded video streaming pipeline using `ScreenCapturer` and `PyAV` for H.264 encoding.
    *   **CRITICAL FLAW**: This file contains logic to *capture* local input and send it to the server, which is redundant. More importantly, it is **missing the logic to receive and inject** input events from the server, making the network client non-functional for remote control.
*   `input_injector.py`: **EMPTY FILE**. This is where the input injection logic for the network client should be, but it is missing.
*   `screen_capture.py`: A wrapper class around the `mss` library for fast, cross-platform screen capturing.
*   `usb_client.py`: A full implementation of a source agent that communicates over a serial (USB) port.
    *   **KEY FINDING**: Unlike the TCP client, this file **contains the complete and correct logic** for receiving `KEY_EVENT` and `MOUSE_EVENT` messages from the Hub and using `pynput` controllers to inject them into the local OS.

### `src/ui/`

*   `app.py`: A comprehensive Streamlit application that serves as the GUI.
    *   Manages starting/stopping the Hub and Agent processes.
    *   Provides a "Receiver Mode" to control the Hub, list clients, and view the active video stream.
    *   Provides a "Sender Mode" to start the local agent.
    *   Includes a high-performance video decoder using `PyAV` that runs in a background thread and displays the video feed.
    *   Implements adaptive frame-skipping to maintain UI responsiveness when receiving high-FPS streams.

### `src/native/`

This directory contains the C++ source code for the high-performance backend.

*   `kvmstream.hpp`: The header file defining the C++ architecture. It defines the `VideoStreamer` class, which uses a three-thread pipeline (capture, encode, network) and other classes for screen capture (`ScreenCapturer`) and encoding (`H264Encoder`).
*   `kvmstream.cpp`: The implementation file.
    *   `ScreenCapturer`: Uses the high-performance **DXGI Desktop Duplication API** on Windows for low-latency screen capture directly from the GPU.
    *   `H264Encoder`: Uses FFmpeg libraries (`libavcodec`, `sws_scale`) to perform H.264 encoding. It intelligently falls back from the NVIDIA hardware encoder (`h264_nvenc`) to the software `libx264` encoder if needed.
    *   `VideoStreamer`: Implements the three-thread pipeline with thread-safe queues, ensuring that screen capture, encoding, and networking happen in parallel without blocking each other.
*   `python_bindings.cpp`: Uses `pybind11` to create the `kvmstream_native` Python module, exposing the C++ classes and functions to the Python application.

### `tests/`

*   `integration/test_video_pipeline.py`: These are high-level tests that use extensive mocking and do not test true integration. They verify some of the logic of the Python video pipeline in isolation.
*   `unit/`: Contains more focused unit tests.
    *   `test_protocol.py`: Tests the message creation and parsing logic.
    *   `test_server.py`: Excellent tests that use real sockets on localhost to verify the server's connection handling, state management, and input forwarding.
    *   `test_client.py`: **KEY FINDING**: These tests attempt to verify the client's input injection logic by calling a `_handle_command` method. However, this method does not exist in the current `src/source_agent/client.py`, confirming that the file is incomplete and the tests are for a more complete version of the code.

---

## 3. Key Findings and Architectural Summary

*   **Strong Architecture**: The project has a very strong and well-thought-out architecture, separating the Hub, Agent, and UI. The use of a high-performance C++ backend with a Python fallback is an excellent design choice.
*   **High-Performance Video**: The video pipeline is the most impressive part of the project. The C++ backend's use of DXGI for capture and a multi-threaded pipeline for processing is professional-grade. The Python fallback is also highly optimized, using `PyAV` and a producer-consumer pattern.
*   **Robust Networking**: The use of TLS for security and separate TCP sockets for control and video is a solid design. The custom framing protocols (both for TCP and serial) are implemented correctly.
*   **Well-Designed UI**: The Streamlit UI is feature-rich and correctly manages background processes, making the system easy to use and monitor.
*   **CRITICAL FLAW - Missing Input Injection**: The primary functionality of remote control is broken for the main network-based client. The `src/source_agent/client.py` file is missing the logic to process incoming keyboard/mouse events from the Hub. The logic *does* exist in `src/source_agent/usb_client.py` and needs to be ported over to the main network client. The unit tests in `tests/unit/source_agent/test_client.py` confirm that this logic was intended to be there.

This concludes my comprehensive analysis of the repository.
