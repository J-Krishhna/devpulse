from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from app.api.connection_manager import manager
from app.db.session import async_session
from app.db.models import Repo
from app.retrieval.hybrid import hybrid_search
from app.generation.llm import stream_answer

router = APIRouter()


@router.websocket("/ws/{repo_id}")
async def websocket_endpoint(websocket: WebSocket, repo_id: str):
    await manager.connect(repo_id, websocket)

    try:
        # Verify repo exists
        async with async_session() as session:
            repo = await session.scalar(
                select(Repo).where(Repo.id == repo_id)
            )
        if not repo:
            await websocket.send_json({"type": "error", "message": "Repo not found"})
            await websocket.close()
            return

        await websocket.send_json({"type": "connected", "repo_id": repo_id})

        # Main message loop
        while True:
            data = await websocket.receive_json()

            if data.get("type") != "query":
                await websocket.send_json({"type": "error", "message": "Unknown message type"})
                continue

            question = data.get("question", "").strip()
            if not question:
                await websocket.send_json({"type": "error", "message": "Empty question"})
                continue

            # Retrieve chunks
            async with async_session() as session:
                chunks = await hybrid_search(session, question, repo_id)

            if not chunks:
                await websocket.send_json({
                    "type": "error",
                    "message": "No relevant code found for that question"
                })
                continue

            # Stream tokens back one by one
            async for token in stream_answer(question, chunks):
                await websocket.send_json({"type": "token", "content": token})

            # Signal completion — frontend uses this to stop the loading state
            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        manager.disconnect(repo_id, websocket)