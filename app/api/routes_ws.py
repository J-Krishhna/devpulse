from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from app.api.connection_manager import manager
from app.db.session import async_session
from app.db.models import Repo
from app.retrieval.hybrid import hybrid_search
from app.generation.llm import stream_answer
from app.config import settings
import asyncio
import json
from redis.asyncio import Redis as AsyncRedis

router = APIRouter()


async def _redis_listener(repo_id: str, websocket: WebSocket, stop_event: asyncio.Event):
    try:
        r = AsyncRedis.from_url(settings.redis_url)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"devpulse:{repo_id}")
        print(f"[redis_listener] subscribed to devpulse:{repo_id}")

        while not stop_event.is_set():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if message and message["type"] == "message":
                print(f"[redis_listener] got message: {message['data']}")
                data = json.loads(message["data"])
                try:
                    await websocket.send_json(data)
                    print(f"[redis_listener] sent to websocket")
                except Exception as e:
                    print(f"[redis_listener] websocket send failed: {e}")
                    break
            await asyncio.sleep(0.05)

    except Exception as e:
        print(f"[redis_listener] crashed: {e}")
    finally:
        await pubsub.unsubscribe()
        await r.aclose()
        print(f"[redis_listener] closed")


@router.websocket("/ws/{repo_id}")
async def websocket_endpoint(websocket: WebSocket, repo_id: str):
    await manager.connect(repo_id, websocket)
    stop_event = asyncio.Event()
    listener_task = asyncio.create_task(
        _redis_listener(repo_id, websocket, stop_event)
    )

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

        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue

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
        pass
    except Exception as e:
        print(f"[ws] error: {e}")
    finally:
        stop_event.set()
        listener_task.cancel()
        manager.disconnect(repo_id, websocket)