from fastapi import WebSocket
from collections import defaultdict
import redis
import json
from app.config import settings

_redis = redis.Redis.from_url(settings.redis_url)


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, repo_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections[repo_id].append(websocket)

    def disconnect(self, repo_id: str, websocket: WebSocket):
        self._connections[repo_id].remove(websocket)

    async def broadcast(self, repo_id: str, message: dict):
        dead = []
        for ws in self._connections[repo_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections[repo_id].remove(ws)

    def publish(self, repo_id: str, message: dict):
        """
        Called from the worker process — publishes to Redis channel.
        The FastAPI process subscribes and forwards to WebSocket clients.
        """
        _redis.publish(f"devpulse:{repo_id}", json.dumps(message))


manager = ConnectionManager()