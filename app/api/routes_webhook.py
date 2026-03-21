import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, Header
from app.config import settings
from app.db.session import async_session
from app.db.models import Repo
from sqlalchemy import select

router = APIRouter()


def _verify_github_signature(payload_bytes: bytes, signature_header: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.github_webhook_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, received)


@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
):
    payload_bytes = await request.body()

    if not _verify_github_signature(payload_bytes, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "push":
        return {"status": "ignored", "event": x_github_event}

    payload = await request.json()

    repo_url = payload.get("repository", {}).get("html_url")
    if not repo_url:
        raise HTTPException(status_code=400, detail="No repository URL in payload")

    async with async_session() as session:
        repo = await session.scalar(
            select(Repo).where(Repo.github_url == repo_url)
        )
        if not repo:
            raise HTTPException(status_code=404, detail=f"Repo not tracked: {repo_url}")
        repo_id = str(repo.id)

    # Enqueue with dramatiq — identical mental model to RQ, different syntax
    from app.workers.ingestion_worker import run_process_push_event
    run_process_push_event.send(repo_id, payload)

    return {"status": "queued", "repo_id": repo_id}