# scripts/fix_repo_url.py
import asyncio, sys
sys.path.append(".")

from app.db.session import async_session
from app.db.models import Repo
from sqlalchemy import update, select

async def main():
    async with async_session() as session:
        # See what's currently in the DB
        repos = (await session.execute(select(Repo))).scalars().all()
        print("Current repos in DB:")
        for r in repos:
            print(f"  id: {r.id}  url: {r.github_url}  status: {r.status}")

        # Update to match exactly what GitHub sends
        await session.execute(
            update(Repo).values(github_url="https://github.com/J-Krishhna/devpulse")
        )
        await session.commit()
        print("\n✅ Updated. Push again.")

asyncio.run(main())