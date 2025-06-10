import threading

class StateManager:
    def __init__(self):
        self.active_client = None
        self.clients = {}
        self.latest_frames = {}
        self.frame_lock = threading.Lock()

    def add_client(self, client_id, client_info):
        self.clients[client_id] = client_info

    def remove_client(self, client_id):
        if client_id in self.clients:
            del self.clients[client_id]
        if client_id in self.latest_frames:
            with self.frame_lock:
                del self.latest_frames[client_id]

    def set_active_client(self, client_id):
        if client_id is None:
            self.active_client = None
            return True
        if client_id in self.clients:
            self.active_client = client_id
            return True
        return False

    def get_active_client(self):
        return self.active_client

    def get_client_info(self, client_id):
        return self.clients.get(client_id)

    def get_all_clients(self):
        return self.clients

    def update_latest_frame(self, client_id, frame):
        with self.frame_lock:
            self.latest_frames[client_id] = frame

    def get_latest_frame(self, client_id):
        with self.frame_lock:
            return self.latest_frames.get(client_id)