import asyncio
import sys
sys.path.append(".")

from uuid import uuid4
from app.db.session import async_session
from app.db.models import Repo
from app.ingestion.embedder import embed_chunks, embed_query
from app.retrieval.vector_store import bulk_insert_chunks, search_chunks, delete_chunks_by_file


# Real function bodies — not toy signatures
SAMPLE_CHUNKS = [
    {
        "file_path": "app/auth.py",
        "function_name": "authenticate_user",
        "start_line": 1,
        "end_line": 10,
        "raw_text": """def authenticate_user(token: str) -> bool:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        return user_id is not None
    except jwt.ExpiredSignatureError:
        return False
    except jwt.InvalidTokenError:
        return False""",
    },
    {
        "file_path": "app/auth.py",
        "function_name": "generate_token",
        "start_line": 12,
        "end_line": 20,
        "raw_text": """def generate_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")""",
    },
    {
        "file_path": "app/billing.py",
        "function_name": "calculate_invoice_total",
        "start_line": 1,
        "end_line": 8,
        "raw_text": """def calculate_invoice_total(items: list) -> float:
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    tax = subtotal * 0.18
    discount = subtotal * 0.05 if subtotal > 1000 else 0
    return subtotal + tax - discount""",
    },
]


async def main():
    async with async_session() as session:

        # 1. Create a test repo row (FK required before inserting chunks)
        repo = Repo(github_url="https://github.com/test/devpulse")
        session.add(repo)
        await session.commit()
        repo_id = repo.id
        print(f"✅ Created test repo: {repo_id}")

        # 2. Embed all chunk texts
        texts = [c["raw_text"] for c in SAMPLE_CHUNKS]
        vectors = embed_chunks(texts)
        print(f"✅ Embedded {len(vectors)} chunks")

        # 3. Attach repo_id and embedding to each chunk dict
        chunks_to_insert = [
            {**chunk, "repo_id": repo_id, "embedding": vectors[i]}
            for i, chunk in enumerate(SAMPLE_CHUNKS)
        ]

        # 4. Insert into pgvector
        await bulk_insert_chunks(session, chunks_to_insert)
        print(f"✅ Inserted {len(chunks_to_insert)} chunks into pgvector")

        # 5. Run a similarity search
        query = "how does user authentication work?"
        query_vec = embed_query(query)
        results = await search_chunks(session, query_vec, repo_id, top_k=3)

        print(f"\n🔍 Query: '{query}'")
        print(f"{'Rank':<6} {'Score':<8} {'Function':<30} {'File'}")
        print("-" * 70)
        for i, r in enumerate(results):
            print(f"{i+1:<6} {r['score']:.4f}   {r['function_name']:<30} {r['file_path']}")

        # 6. Test delete
        deleted = await delete_chunks_by_file(session, repo_id, "app/auth.py")
        print(f"\n✅ Deleted {deleted} chunks from app/auth.py")

        # Search again — auth chunks should be gone
        results_after = await search_chunks(session, query_vec, repo_id, top_k=3)
        print(f"Results after delete: {len(results_after)} chunk(s) remaining")
        for r in results_after:
            print(f"  → {r['function_name']} ({r['file_path']})")


asyncio.run(main())