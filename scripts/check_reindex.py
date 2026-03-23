# scripts/check_reindex.py
import asyncio, sys
sys.path.append(".")

from app.db.session import async_session
from app.db.models import File
from sqlalchemy import select

async def main():
    async with async_session() as session:
        files = (await session.execute(select(File))).scalars().all()
        print(f"{'File path':<50} {'Last indexed'}")
        print("-" * 70)
        for f in files:
            print(f"{f.file_path:<50} {f.last_indexed_at}")

asyncio.run(main())