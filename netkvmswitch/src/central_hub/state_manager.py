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

    def find_client_by_ip(self, ip_address):
        """Finds a client by its IP address. Assumes one client per IP."""
        for client_id, info in self.clients.items():
            if client_id[0] == ip_address:
                return client_id
        return None

    def add_video_socket(self, client_id, video_socket):
        """Associates a video socket with a client."""
        if client_id in self.clients:
            self.clients[client_id]['video_conn'] = video_socket

    def remove_video_socket(self, client_id):
        """Removes the video socket association from a client."""
        if client_id in self.clients and 'video_conn' in self.clients[client_id]:
            del self.clients[client_id]['video_conn']