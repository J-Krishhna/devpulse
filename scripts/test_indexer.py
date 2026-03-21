import asyncio
import sys
sys.path.append(".")

from app.db.session import async_session
from app.db.models import Repo
from app.ingestion.indexer import ingest_file, ingest_folder
from app.ingestion.embedder import embed_query
from app.retrieval.vector_store import search_chunks


async def main():
    async with async_session() as session:

        # Create a test repo
        repo = Repo(github_url="https://github.com/test/devpulse-indexer-test")
        session.add(repo)
        await session.commit()
        repo_id = repo.id
        print(f"✅ Created repo: {repo_id}\n")

        # ── Test 1: ingest a single file ──────────────────────────────────────
        print("── Test 1: Single file ingest ──")
        content = open("app/ingestion/embedder.py").read()
        result = await ingest_file(session, repo_id, "app/ingestion/embedder.py", content)
        print(f"Status:  {result['status']}")
        print(f"Chunks:  {result.get('chunks')}")
        print()

        # ── Test 2: same file again — should skip (hash unchanged) ────────────
        print("── Test 2: Re-ingest same file (should skip) ──")
        result2 = await ingest_file(session, repo_id, "app/ingestion/embedder.py", content)
        print(f"Status:  {result2['status']}")
        print(f"Reason:  {result2.get('reason')}")
        print()

        # ── Test 3: modified file — should re-index ───────────────────────────
        print("── Test 3: Modified file (should re-index) ──")
        modified = content + "\n# modified"
        result3 = await ingest_file(session, repo_id, "app/ingestion/embedder.py", modified)
        print(f"Status:   {result3['status']}")
        print(f"Chunks:   {result3.get('chunks')}")
        print(f"Replaced: {result3.get('replaced')} old chunks deleted")
        print()

        # ── Test 4: ingest entire app/ folder ─────────────────────────────────
        print("── Test 4: Folder ingest ──")
        folder_result = await ingest_folder(session, repo_id, "app/")
        print(f"Indexed: {len(folder_result['indexed'])} files")
        print(f"Skipped: {len(folder_result['skipped'])} files")
        print(f"Errors:  {len(folder_result['errors'])} files")
        for e in folder_result["errors"]:
            print(f"  ❌ {e['file']}: {e['error']}")
        print()

        # ── Test 5: end-to-end query against indexed content ──────────────────
        print("── Test 5: Query against indexed content ──")
        query = "how are text chunks embedded into vectors?"
        query_vec = embed_query(query)
        results = await search_chunks(session, query_vec, repo_id, top_k=3)

        print(f"Query: '{query}'")
        print(f"{'Rank':<6} {'Score':<8} {'Function':<30} {'File'}")
        print("-" * 70)
        for i, r in enumerate(results):
            print(f"{i+1:<6} {r['score']:.4f}   {r['function_name']:<30} {r['file_path']}")


asyncio.run(main())