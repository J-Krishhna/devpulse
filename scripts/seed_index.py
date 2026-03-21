# scripts/seed_index.py
import asyncio, sys
sys.path.append(".")

from app.db.session import async_session
from app.db.models import Repo
from app.ingestion.indexer import ingest_folder
from sqlalchemy import update

async def main():
    async with async_session() as session:
        repo = Repo(github_url="https://github.com/test/devpulse", status="indexed")
        session.add(repo)
        await session.commit()
        print(f"repo_id: {repo.id}")

        result = await ingest_folder(session, repo.id, "app/")
        print(f"Indexed: {len(result['indexed'])} files")
        print(f"Errors:  {result['errors']}")

asyncio.run(main())