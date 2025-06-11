import asyncio
import logging
import socket
import threading
import subprocess
import signal
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
import os
import sys

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from common.protocol import create_message, parse_message
from common.config import config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - WEB_UI - %(message)s')

app = FastAPI()

# --- Global State ---
agent_process = None

# --- Hub Connection ---
class HubConnector:
    def __init__(self):
        self.control_socket = None
        self.video_socket = None
        self.connected = False

    def connect(self):
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.connect((config.ui.server_host, config.server.ui_control_port))
            self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.video_socket.connect((config.ui.server_host, config.server.ui_video_port))
            self.connected = True
            logging.info("Successfully connected to the hub.")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to hub: {e}")
            return False

    def send_command(self, command_type, payload=None):
        if not self.connected: return None
        try:
            message = create_message(command_type, payload or {})
            self.control_socket.sendall(message)
            data = self.control_socket.recv(4096)
            return parse_message(data).get('payload', {}) if data else None
        except Exception:
            self.connected = False
            return None

hub_connector = HubConnector()

# --- WebSocket Management ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: bytes):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_bytes(message)
            except Exception:
                dead_connections.append(connection)
        
        for connection in dead_connections:
            self.active_connections.remove(connection)

manager = ConnectionManager()

# --- API Endpoints ---
@app.get("/api/clients")
async def get_clients():
    clients = hub_connector.send_command("get_clients")
    return clients or {"clients": {}}

@app.post("/api/clients/active")
async def set_active_client(client_info: dict):
    address = client_info.get("address")
    logging.info(f"Request to set active client to: {address}")
    response = hub_connector.send_command("set_active_client", {"address": address})
    return response or {"success": False, "message": "Failed to set active client"}

@app.post("/api/hub/set_input_forwarding")
async def set_input_forwarding(payload: dict):
    enabled = payload.get("enabled", False)
    response = hub_connector.send_command("set_input_forwarding", {"enabled": enabled})
    return response or {"success": False, "message": "Failed to set input forwarding"}

@app.post("/api/agent/start")
async def start_agent():
    global agent_process
    if agent_process and agent_process.poll() is None:
        return {"success": False, "message": "Agent is already running."}
    
    src_dir = os.path.join(os.path.dirname(__file__), '..')
    agent_process = subprocess.Popen(
        [sys.executable, "-m", "source_agent.agent_runner"],
        cwd=src_dir,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )
    return {"success": True, "message": "Agent started."}

@app.post("/api/agent/stop")
async def stop_agent():
    global agent_process
    if agent_process and agent_process.poll() is None:
        if sys.platform == "win32":
            agent_process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            agent_process.terminate()
        agent_process.wait(timeout=5)
        agent_process = None
        return {"success": True, "message": "Agent stopped."}
    return {"success": False, "message": "Agent not running."}

@app.post("/api/agent/restart")
async def restart_agent(payload: dict):
    address = payload.get("address")
    if not address:
        return {"success": False, "message": "Address not provided."}
    response = hub_connector.send_command("restart_agent", {"address": address})
    return response or {"success": False, "message": "Failed to send restart command."}

@app.post("/api/io/event")
async def forward_io_event(payload: dict):
    response = hub_connector.send_command("forward_io_event", payload)
    return response or {"success": False, "message": "Failed to forward I/O event"}

@app.post("/api/hub/shutdown")
async def shutdown_hub():
    logging.warning("Shutdown command received from UI. Shutting down.")
    # This is a bit of a hack, but it's a reliable way to stop the uvicorn server
    # which will then allow the run_ui.py script to terminate the hub process.
    os.kill(os.getpid(), signal.SIGINT)
    return {"success": True, "message": "Shutdown signal sent."}

# --- WebSocket Endpoint ---
@app.websocket("/ws/video")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await asyncio.sleep(3600) # Keep connection open
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logging.info("Client disconnected from video websocket.")

# --- Background Task for Video Forwarding ---
def recv_all(sock, n):
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet: return None
        data.extend(packet)
    return data

async def forward_video_stream():
    while not hub_connector.connected:
        logging.info("Attempting to connect to hub...")
        hub_connector.connect()
        await asyncio.sleep(2)

    while True:
        try:
            # The hub now sends a message framed with a 4-byte length header.
            # This message contains the padded address and the H.264 data.
            size_bytes = await asyncio.to_thread(recv_all, hub_connector.video_socket, 4)
            if not size_bytes:
                logging.warning("Hub video stream disconnected. Reconnecting...")
                hub_connector.connect()
                continue

            message_size = int.from_bytes(size_bytes, 'big')
            message_data = await asyncio.to_thread(recv_all, hub_connector.video_socket, message_size)
            if not message_data:
                continue

            # Directly forward the entire message (tagged packet) to the UI
            await manager.broadcast(message_data)

        except Exception as e:
            logging.error(f"Video forwarding error: {e}")
            hub_connector.connected = False
            while not hub_connector.connected:
                await asyncio.sleep(2)
                hub_connector.connect()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(forward_video_stream())

# --- Static File Serving ---
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), 'static/index.html'))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
