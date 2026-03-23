from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from app.api.connection_manager import manager
from app.db.session import async_session
from app.db.models import Repo
from app.retrieval.hybrid import hybrid_search
from app.generation.llm import stream_answer
from app.config import settings
import asyncio
import redis
import json

router = APIRouter()


async def _redis_listener(repo_id: str, websocket: WebSocket):
    """
    Runs as a background task for each WebSocket connection.
    Subscribes to the repo's Redis channel and forwards any
    index_progress events to the connected client.
    """
    r = redis.Redis.from_url(settings.redis_url)
    pubsub = r.pubsub()
    pubsub.subscribe(f"devpulse:{repo_id}")

    try:
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True)
            if message and message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)
            await asyncio.sleep(0.1)   # poll every 100ms
    except Exception:
        pass
    finally:
        pubsub.unsubscribe()
        pubsub.close()


@router.websocket("/ws/{repo_id}")
async def websocket_endpoint(websocket: WebSocket, repo_id: str):
    await manager.connect(repo_id, websocket)

    try:
        async with async_session() as session:
            repo = await session.scalar(
                select(Repo).where(Repo.id == repo_id)
            )
        if not repo:
            await websocket.send_json({"type": "error", "message": "Repo not found"})
            await websocket.close()
            return

        await websocket.send_json({"type": "connected", "repo_id": repo_id})

        # Start Redis listener as a background task
        listener_task = asyncio.create_task(_redis_listener(repo_id, websocket))

        while True:
            data = await websocket.receive_json()

            if data.get("type") != "query":
                await websocket.send_json({"type": "error", "message": "Unknown message type"})
                continue

            question = data.get("question", "").strip()
            if not question:
                await websocket.send_json({"type": "error", "message": "Empty question"})
                continue

            async with async_session() as session:
                chunks = await hybrid_search(session, question, repo_id)

            if not chunks:
                await websocket.send_json({
                    "type": "error",
                    "message": "No relevant code found for that question"
                })
                continue

            async for token in stream_answer(question, chunks):
                await websocket.send_json({"type": "token", "content": token})

            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        manager.disconnect(repo_id, websocket)
        listener_task.cancel()