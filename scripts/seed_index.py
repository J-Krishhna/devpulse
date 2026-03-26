# scripts/seed_index.py
import asyncio, sys
sys.path.append(".")

from app.db.session import async_session
from app.db.models import Repo
from app.ingestion.indexer import ingest_folder
from sqlalchemy import update, select

async def main():
    async with async_session() as session:
        # Get your repo
        repos = (await session.execute(select(Repo))).scalars().all()
        for r in repos:
            print(f"id: {r.id}  status: {r.status}")

        repo_id = input("\nPaste the repo_id to index: ").strip()

        print("Indexing...")
        result = await ingest_folder(session, repo_id, "app/")
        print(f"Indexed: {len(result['indexed'])} files")
        print(f"Errors:  {result['errors']}")

        # Mark as indexed
        await session.execute(
            update(Repo).where(Repo.id == repo_id).values(status="indexed")
        )
        await session.commit()
        print("✅ Status set to indexed")

asyncio.run(main())




# # scripts/seed_index.py
# import asyncio, sys
# sys.path.append(".")

# from app.db.session import async_session
# from app.db.models import Repo
# from app.ingestion.indexer import ingest_folder
# from sqlalchemy import update

# async def main():
#     async with async_session() as session:
#         repo = Repo(github_url="https://github.com/test/devpulse", status="indexed")
#         session.add(repo)
#         await session.commit()
#         print(f"repo_id: {repo.id}")

#         result = await ingest_folder(session, repo.id, "app/")
#         print(f"Indexed: {len(result['indexed'])} files")
#         print(f"Errors:  {result['errors']}")

# asyncio.run(main())