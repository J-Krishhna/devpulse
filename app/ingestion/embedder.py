from sentence_transformers import SentenceTransformer
from typing import List
import numpy as np

# Module-level singleton — model loads once when this file is first imported.
# Every subsequent call to embed_chunks() reuses the same loaded model.
# If you put this inside the function, the model reloads on every call — ~3 seconds each time.
_model = SentenceTransformer("BAAI/bge-base-en-v1.5")


def embed_chunks(texts: List[str]) -> List[List[float]]:
    """
    Embed a list of text strings using BGE.
    Returns a list of 768-dimensional float vectors.
    One vector per input string, same order.
    """
    if not texts:
        return []

    # BGE-specific instruction prefix for passage embedding.
    # BGE was trained with this prefix on the *document* side (not query side).
    # Omitting it slightly degrades retrieval quality.
    prefixed = [f"Represent this code snippet for retrieval: {t}" for t in texts]

    embeddings = _model.encode(
        prefixed,
        batch_size=32,        # process 32 strings at a time — memory vs speed tradeoff
        show_progress_bar=False,
        normalize_embeddings=True,   # L2-normalize so cosine similarity = dot product
    )

    # encode() returns a numpy array — convert to plain Python lists for JSON serialisation
    # and pgvector compatibility
    return embeddings.tolist()


def embed_query(query: str) -> List[float]:
    """
    Embed a single query string.
    Uses a different BGE prefix — BGE uses asymmetric retrieval:
    documents and queries get different prefixes.
    """
    prefixed = f"Represent this question for searching relevant code: {query}"
    embedding = _model.encode(
        prefixed,
        normalize_embeddings=True,
    )
    return embedding.tolist()
"# test" 
"# test" 
"# test2" 
"# I_LOVe_BALAHARSHINI" 
"# I_LOVE_BALAHARSHINI" 
"# I_LOVe_BALAHARSHINIIIIII" 
"# I_LOVe_BALAHARSHINIIIIII" 
"# I_LOVE_BALAHARSHINI" 
