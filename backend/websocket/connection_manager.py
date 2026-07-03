from typing import Set, Dict
from fastapi import WebSocket
from collections import defaultdict

class ConnectionManager:
    def __init__(self):
        # Maps group_id to a set of active WebSocket connections
        self.group_rooms: Dict[int, Set[WebSocket]] = defaultdict(set)
        # Track which group a socket belongs to for easy cleanup
        self.socket_to_group: Dict[WebSocket, int] = {}

    async def connect(self, websocket: WebSocket, group_id: int):
        """Accept connection and add it to the specific group room."""
        await websocket.accept()
        self.group_rooms[group_id].add(websocket)
        self.socket_to_group[websocket] = group_id

    def disconnect(self, websocket: WebSocket):
        """Remove connection from active tracking."""
        group_id = self.socket_to_group.get(websocket)
        if group_id is not None:
            if websocket in self.group_rooms[group_id]:
                self.group_rooms[group_id].remove(websocket)
            del self.socket_to_group[websocket]

    async def send_json_message(self, message: dict, websocket: WebSocket):
        """Send formatted JSON payloads directly to a single socket client."""
        await websocket.send_json(message)

    async def send_binary_message(self, data: bytes, websocket: WebSocket):
        """Send raw binary payloads (audio buffers) to a single socket client."""
        await websocket.send_bytes(data)

    async def broadcast_json_to_group(self, message: dict, group_id: int, exclude: WebSocket = None):
        """Broadcast a JSON message to all connected clients in a specific group."""
        if group_id in self.group_rooms:
            for connection in self.group_rooms[group_id]:
                if connection == exclude:
                    continue
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

manager = ConnectionManager()
