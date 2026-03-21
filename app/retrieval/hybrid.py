from app.retrieval.vector_store import search_chunks
from app.ingestion.embedder import embed_query


def _rrf_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """
    Reciprocal Rank Fusion — merges two ranked lists into one.
    Score for each result = 1/(k + rank) summed across both lists.
    k=60 is the standard default from the original RRF paper.
    Higher combined score = better.
    """
    scores: dict[str, float] = {}
    chunks_by_id: dict[str, dict] = {}

    for rank, chunk in enumerate(vector_results):
        cid = chunk["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
        chunks_by_id[cid] = chunk

    for rank, chunk in enumerate(bm25_results):
        cid = chunk["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
        chunks_by_id[cid] = chunk

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
    return [chunks_by_id[cid] for cid in sorted_ids]


async def hybrid_search(
    session,
    query: str,
    repo_id: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Full retrieval pipeline:
    1. Embed query
    2. Vector search (top 20)
    3. BM25 keyword search (top 20)
    4. RRF fusion
    5. Return top_k

    Reranker is Phase 2 — adding it here later is one function call.
    """
    query_vec = embed_query(query)

    # Vector search
    vector_results = await search_chunks(session, query_vec, repo_id, top_k=20)

    # BM25 search — build on the fly from what's already in vector_results
    # Full BM25 index over all DB chunks comes in Phase 2
    # For now: keyword filter over the vector candidates
    bm25_results = _keyword_filter(query, vector_results)

    # Fuse
    fused = _rrf_fusion(vector_results, bm25_results)

    return fused[:top_k]


def _keyword_filter(query: str, chunks: list[dict]) -> list[dict]:
    """
    Lightweight keyword re-ranking over vector results.
    Scores chunks by how many query terms appear in the raw text.
    Stands in for full BM25 until the index is built in Phase 2.
    """
    query_terms = set(query.lower().split())
    scored = []
    for chunk in chunks:
        text_lower = chunk["raw_text"].lower()
        hits = sum(1 for term in query_terms if term in text_lower)
        scored.append((hits, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored]