import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from app.db.models import Repo, File, Chunk
from app.ingestion.ast_chunker import chunk_python_file
from app.ingestion.embedder import embed_chunks
from app.retrieval.vector_store import bulk_insert_chunks, delete_chunks_by_file


SUPPORTED_EXTENSIONS = {".py"}   # .js, .ts coming in Phase 5


def compute_hash(content: str) -> str:
    """SHA256 of file content — used to detect whether a file actually changed."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def ingest_file(
    session: AsyncSession,
    repo_id: str,
    file_path: str,
    content: str,   
    force: bool = False,
) -> dict:
    """
    Ingest a single file into the vector store.

    Steps:
    1. Compute SHA256 hash of content
    2. Check if file already exists with same hash — skip if unchanged
    3. Delete old chunks if file was previously indexed
    4. AST parse → embed → bulk insert new chunks
    5. Upsert file record with new hash

    Returns a status dict describing what happened.
    """
    ext = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""
    if ext not in SUPPORTED_EXTENSIONS:
        return {"status": "skipped", "reason": "unsupported extension", "file": file_path}

    new_hash = compute_hash(content)

    # Check if this file is already indexed with the same content
    existing_file = await session.scalar(
        select(File).where(File.repo_id == repo_id).where(File.file_path == file_path)
    )

    if existing_file and existing_file.file_hash == new_hash and not force:
        return {"status": "skipped", "reason": "unchanged", "file": file_path}

    # Delete old chunks if file was previously indexed
    deleted_count = 0
    if existing_file:
        deleted_count = await delete_chunks_by_file(session, repo_id, file_path)

    # Parse into chunks
    chunks = chunk_python_file(file_path, content)
    if not chunks:
        return {"status": "skipped", "reason": "no chunks extracted", "file": file_path}

    # Embed all chunks in one batch call
    texts = [c["raw_text"] for c in chunks]
    vectors = embed_chunks(texts)

    # Attach repo_id and embedding
    chunks_to_insert = [
        {**chunk, "repo_id": repo_id, "embedding": vectors[i]}
        for i, chunk in enumerate(chunks)
    ]

    # Insert into pgvector
    await bulk_insert_chunks(session, chunks_to_insert)

    # Upsert the file record
    if existing_file:
        await session.execute(
            update(File)
            .where(File.repo_id == repo_id)
            .where(File.file_path == file_path)
            .values(file_hash=new_hash)
        )
    else:
        session.add(File(repo_id=repo_id, file_path=file_path, file_hash=new_hash))

    await session.commit()

    return {
        "status": "indexed",
        "file": file_path,
        "chunks": len(chunks),
        "replaced": deleted_count,
    }


async def ingest_folder(
    session: AsyncSession,
    repo_id: str,
    folder_path: str,
) -> dict:
    """
    Walk a local folder and ingest every supported file.
    This is your local stand-in for the GitHub API bulk fetch — same logic,
    just reading from disk instead of HTTP.
    Used for testing Phase 1 end-to-end before GitHub integration in Phase 2.
    """
    import os

    results = {"indexed": [], "skipped": [], "errors": []}

    for root, dirs, files in os.walk(folder_path):
        # Skip common noise directories
        dirs[:] = [
            d for d in dirs
            if d not in {"__pycache__", ".git", "venv", "node_modules", ".env"}
        ]

        for filename in files:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, folder_path).replace("\\", "/")

            ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()

                result = await ingest_file(session, repo_id, rel_path, content)

                if result["status"] == "indexed":
                    results["indexed"].append(result)
                else:
                    results["skipped"].append(result)

            except Exception as e:
                results["errors"].append({"file": rel_path, "error": str(e)})

    return results