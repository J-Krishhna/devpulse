# scripts/check_repos.py
import asyncio, sys
sys.path.append(".")

from app.db.session import async_session
from app.db.models import Repo
from sqlalchemy import select

async def main():
    async with async_session() as session:
        repos = (await session.execute(select(Repo))).scalars().all()
        for r in repos:
            print(f"id: {r.id}  status: {r.status}  url: {r.github_url}")

asyncio.run(main())