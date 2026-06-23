from typing import Set
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Set of active WebSocket connections
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept connection and add it to the tracked set."""
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove connection from active tracking."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_json_message(self, message: dict, websocket: WebSocket):
        """Send formatted JSON payloads directly to a single socket client."""
        if websocket in self.active_connections:
            await websocket.send_json(message)

    async def send_binary_message(self, data: bytes, websocket: WebSocket):
        """Send raw binary payloads (audio buffers) to a single socket client."""
        if websocket in self.active_connections:
            await websocket.send_bytes(data)

    async def broadcast_json(self, message: dict):
        """Broadcast a JSON message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Connection might be dead, handled during disconnection cleanup loop
                pass

manager = ConnectionManager()
