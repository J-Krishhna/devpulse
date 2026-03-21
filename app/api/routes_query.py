from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.db.session import get_session
from app.db.models import Repo
from app.retrieval.hybrid import hybrid_search
from app.generation.llm import stream_answer
from sqlalchemy import select

router = APIRouter()


class QueryRequest(BaseModel):
    repo_id: str
    question: str


@router.post("/query")
async def query_repo(
    request: QueryRequest,
    session: AsyncSession = Depends(get_session),
):
    # Verify repo exists and is indexed
    repo = await session.scalar(
        select(Repo).where(Repo.id == request.repo_id)
    )
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")
    if repo.status != "indexed":
        raise HTTPException(
            status_code=400,
            detail=f"Repo is not indexed yet. Current status: {repo.status}"
        )

    # Retrieve relevant chunks
    chunks = await hybrid_search(session, request.question, request.repo_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="No relevant chunks found")

    # Stream the answer back token by token
    async def token_stream():
        async for token in stream_answer(request.question, chunks):
            yield token

    return StreamingResponse(token_stream(), media_type="text/plain")