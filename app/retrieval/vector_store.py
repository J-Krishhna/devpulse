from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text
from pgvector.sqlalchemy import Vector
# from uuid import UUID
from app.db.models import Chunk


async def bulk_insert_chunks(session: AsyncSession, chunks: list[dict]) -> None:
    """
    Insert a list of chunk dicts into the DB.
    Each dict must have: repo_id, file_path, function_name,
                         start_line, end_line, raw_text, embedding
    """
    objects = [Chunk(**chunk) for chunk in chunks]
    session.add_all(objects)
    await session.commit()


async def search_chunks(session, query_vector, repo_id: str, top_k: int = 20) -> list[dict]:
    """
    Find the top_k most similar chunks to query_vector within a repo.
    Uses cosine distance — lower distance = more similar.
    The <=> operator is pgvector's cosine distance operator.
    """
    results = await session.execute(
        select(
            Chunk,
            Chunk.embedding.cosine_distance(query_vector).label("distance"),
        )
        .where(Chunk.repo_id == repo_id)
        .order_by("distance")
        .limit(top_k)
    )

    rows = results.all()
    return [
        {
            "chunk_id": str(row.Chunk.id),
            "file_path": row.Chunk.file_path,
            "function_name": row.Chunk.function_name,
            "start_line": row.Chunk.start_line,
            "end_line": row.Chunk.end_line,
            "raw_text": row.Chunk.raw_text,
            "score": 1 - row.distance,   # convert distance → similarity (1 = identical)
        }
        for row in rows
    ]


async def delete_chunks_by_file(session, repo_id: str, file_path: str) -> int:
    """
    Delete all chunks belonging to a specific file.
    Called before re-indexing a modified file.
    Returns count of deleted rows.
    """
    result = await session.execute(
        delete(Chunk)
        .where(Chunk.repo_id == repo_id)
        .where(Chunk.file_path == file_path)
    )
    await session.commit()
    return result.rowcount