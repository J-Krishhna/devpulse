from fastapi import WebSocket
from collections import defaultdict


class ConnectionManager:
    """
    Tracks active WebSocket connections per repo.
    Allows broadcasting index progress events to all clients
    watching a specific repo.
    """

    def __init__(self):
        # repo_id → list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, repo_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections[repo_id].append(websocket)

    def disconnect(self, repo_id: str, websocket: WebSocket):
        self._connections[repo_id].remove(websocket)

    async def broadcast(self, repo_id: str, message: dict):
        """Send a message to every client watching this repo."""
        dead = []
        for ws in self._connections[repo_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        # Clean up disconnected clients
        for ws in dead:
            self._connections[repo_id].remove(ws)


# Module-level singleton — shared across all routes
manager = ConnectionManager()