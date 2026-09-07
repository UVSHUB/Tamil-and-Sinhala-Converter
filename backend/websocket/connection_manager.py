from typing import Set, Dict
from fastapi import WebSocket

MAX_CALLS_PER_ROOM = 10  # Maximum 10 active call channels per room cluster

class ConnectionManager:
    def __init__(self):
        # Map of room_id -> Set of active WebSocket connections
        self.rooms: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str = "default"):
        """Accept connection and add it to the specified room."""
        await websocket.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = set()
        
        # Enforce maximum concurrent callers per room (10 calls max)
        if len(self.rooms[room_id]) >= MAX_CALLS_PER_ROOM * 2:
            await websocket.send_json({
                "type": "error",
                "payload": {"message": f"Room '{room_id}' has reached maximum concurrent call capacity ({MAX_CALLS_PER_ROOM} calls)."}
            })
            await websocket.close(code=1008, reason="Room full")
            return False

        self.rooms[room_id].add(websocket)
        return True

    def disconnect(self, websocket: WebSocket, room_id: str = "default"):
        """Remove connection from the room tracking."""
        if room_id in self.rooms and websocket in self.rooms[room_id]:
            self.rooms[room_id].remove(websocket)
            if not self.rooms[room_id]:
                del self.rooms[room_id]

    async def send_json_message(self, message: dict, websocket: WebSocket):
        """Send formatted JSON payloads directly to a single socket client."""
        # Simple search across rooms to verify active connection
        is_active = any(websocket in s for s in self.rooms.values())
        if is_active:
            await websocket.send_json(message)

    async def send_binary_message(self, data: bytes, websocket: WebSocket):
        """Send raw binary payloads (audio buffers) to a single socket client."""
        is_active = any(websocket in s for s in self.rooms.values())
        if is_active:
            await websocket.send_bytes(data)

    async def broadcast_json_except(self, message: dict, exclude: WebSocket, room_id: str = "default"):
        """Broadcast a JSON message to all clients in the room except the excluded one."""
        if room_id in self.rooms:
            for connection in self.rooms[room_id]:
                if connection != exclude:
                    try:
                        await connection.send_json(message)
                    except Exception:
                        pass

    async def broadcast_bytes_except(self, data: bytes, exclude: WebSocket, room_id: str = "default"):
        """Broadcast binary audio payload to all clients in the room except the excluded one."""
        if room_id in self.rooms:
            for connection in self.rooms[room_id]:
                if connection != exclude:
                    try:
                        await connection.send_bytes(data)
                    except Exception:
                        pass

manager = ConnectionManager()
