import asyncio
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from app.config import settings

broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(broker)


@dramatiq.actor
def run_process_push_event(repo_id: str, payload: dict):
    """
    Dramatiq actor — this is what gets enqueued and run by the worker.
    Dramatiq calls this synchronously in a thread, so we spin up
    an event loop for our async ingestion code.
    """
    return asyncio.run(process_push_event(repo_id, payload))


async def process_push_event(repo_id: str, payload: dict) -> dict:
    from app.db.session import async_session
    from app.db.models import Repo, File, Chunk
    from app.ingestion.indexer import ingest_file
    from sqlalchemy import select, delete

    commits = payload.get("commits", [])

    removed, modified, added = set(), set(), set()
    for commit in commits:
        removed.update(commit.get("removed", []))
        modified.update(commit.get("modified", []))
        added.update(commit.get("added", []))

    modified -= added

    results = {"removed": [], "indexed": [], "skipped": [], "errors": []}

    async with async_session() as session:

        for file_path in removed:
            try:
                await session.execute(
                    delete(Chunk)
                    .where(Chunk.repo_id == repo_id)
                    .where(Chunk.file_path == file_path)
                )
                await session.execute(
                    delete(File)
                    .where(File.repo_id == repo_id)
                    .where(File.file_path == file_path)
                )
                await session.commit()
                results["removed"].append(file_path)
            except Exception as e:
                results["errors"].append({"file": file_path, "error": str(e)})

        for file_path in added | modified:
            try:
                content = await _fetch_file_from_github(repo_id, file_path, session)
                if content is None:
                    results["skipped"].append({"file": file_path, "reason": "could not fetch"})
                    continue

                result = await ingest_file(session, repo_id, file_path, content)
                if result["status"] == "indexed":
                    results["indexed"].append(result)
                else:
                    results["skipped"].append(result)

            except Exception as e:
                results["errors"].append({"file": file_path, "error": str(e)})

    from app.api.connection_manager import manager
    summary = (
        f"Re-indexed {len(results['indexed'])} file(s), "
        f"removed {len(results['removed'])} file(s)"
    )
    await manager.broadcast(repo_id, {
        "type": "index_progress",
        "message": summary,
        "details": results,
    })

    print(f"[worker] done — {results}")
    return results




async def _fetch_file_from_github(repo_id: str, file_path: str, session) -> str | None:
    import httpx
    from app.db.models import Repo
    from sqlalchemy import select

    repo = await session.scalar(select(Repo).where(Repo.id == repo_id))
    if not repo:
        return None

    base = repo.github_url.replace("https://github.com/", "https://raw.githubusercontent.com/")
    url = f"{base}/main/{file_path}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url)
        if response.status_code == 200:
            return response.text
        return None