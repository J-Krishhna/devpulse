import sys
sys.path.append(".")   # lets Python find the app/ package from the project root

from app.ingestion.embedder import embed_chunks, embed_query
import numpy as np

# --- Test 1: Basic shape check ---
texts = [
    "def authenticate_user(token: str) -> bool: ...",
    "def calculate_invoice_total(items: list) -> float: ...",
    "class DatabaseConnection: ...",
]

vectors = embed_chunks(texts)

print(f"Input count:   {len(texts)}")
print(f"Output count:  {len(vectors)}")
print(f"Vector length: {len(vectors[0])}  ← should be 768")
print()

# --- Test 2: Semantic similarity ---
# These two should be close (both about auth)
# The third should be far (unrelated topic)
auth_fn   = embed_chunks(["def authenticate_user(token): verify JWT and return user"])[0]
login_fn  = embed_chunks(["def login(username, password): check credentials and issue token"])[0]
invoice_fn = embed_chunks(["def calculate_invoice_total(items): sum prices and apply tax"])[0]

def cosine_sim(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

sim_related   = cosine_sim(auth_fn, login_fn)
sim_unrelated = cosine_sim(auth_fn, invoice_fn)

print(f"Auth ↔ Login similarity:    {sim_related:.4f}   ← should be HIGH (>0.7)")
print(f"Auth ↔ Invoice similarity:  {sim_unrelated:.4f}  ← should be LOW (<0.5)")
print()

# --- Test 3: Query vs chunk ---
query_vec  = embed_query("how does user authentication work?")
chunk_vec  = embed_chunks(["def authenticate_user(token): verify JWT and return user"])[0]
query_sim  = cosine_sim(query_vec, chunk_vec)

print(f"Query ↔ Auth chunk similarity: {query_sim:.4f}  ← should be reasonably high (>0.5)")