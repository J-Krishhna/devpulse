# DevPulse ⚡
 
A real-time codebase intelligence platform. Point it at a GitHub repo, ask questions in natural language, get answers that stream back token-by-token with source file citations.
 
> **"What does the payment module do and where is it called from?"**
> — answered in seconds, grounded in your actual code.
 
---
 
## Demo
 
A developer pushes code to GitHub. Within 30 seconds, DevPulse has re-indexed the changed files. A teammate opens the dashboard and asks a question — the answer streams back in real time with citations to the exact functions and line numbers.
 
---
 
## Evaluation
 
Scored with [RAGAs](https://github.com/explodinggradients/ragas) on a golden dataset of 20 questions about the DevPulse codebase itself — questions with known ground truth answers.
 
| Metric | Score |
|---|---|
| Faithfulness | **0.87** |
| Answer Relevancy | **0.76** |
| Context Precision | **0.71** |
| Context Recall | 0.35 |
 
**Faithfulness of 0.87** means answers are grounded in retrieved code and rarely contradict it. Low context recall is a known limitation of the current keyword filter — a full BM25 index over all DB chunks is planned for Phase 5.
 
---
 
## Architecture
 
```
GitHub Push
    │
    ▼
POST /webhook/github
    │  HMAC signature validated
    │  returns 200 immediately
    ▼
Redis Queue (Dramatiq)
    │
    ▼
Ingestion Worker
    ├── fetch changed files from GitHub API
    ├── compute SHA256 hash → skip if unchanged
    ├── delete old vectors for modified files
    ├── AST parse with tree-sitter → one chunk per function/class
    ├── batch embed with BAAI/bge-base-en-v1.5
    └── bulk insert into pgvector
 
WebSocket /ws/{repo_id}
    │
    ▼
Query Pipeline
    ├── embed query with BGE
    ├── pgvector ANN search → top 20 by cosine similarity
    ├── keyword filter → re-rank by term frequency
    ├── RRF fusion → merge both ranked lists
    ├── top 5 chunks assembled with citations
    └── Groq Llama 3.3 70B streaming → tokens forwarded over WebSocket
```
 
---
 
## Stack and Why
 
| Component | Choice | Why |
|---|---|---|
| Embedding | BAAI/bge-base-en-v1.5 | Top-5 MTEB retrieval, runs locally on CPU, zero cost |
| Vector DB | PostgreSQL + pgvector | One DB for relational + vectors, ACID, no separate service |
| LLM | Groq — Llama 3.3 70B | 300+ tokens/sec, free tier, OpenAI-compatible |
| LLM fallback | Gemini 2.0 Flash | Used when Groq rate-limits |
| Job queue | Redis + Dramatiq | Webhook must return 200 in <10s — ingestion runs async |
| AST parser | tree-sitter | Industry standard, preserves function/class boundaries |
| Keyword search | BM25 (rank-bm25) | Catches exact function name matches semantic search misses |
| Framework | FastAPI + SQLAlchemy async | Full async stack — WebSocket streaming + concurrent workers |
 
### Key design decisions
 
**AST chunking over sliding window** — a 500-token window cuts across function boundaries and produces chunks that make no sense in isolation. AST chunking keeps each function and class intact — semantically complete, always a real unit of logic.
 
**pgvector over Pinecone/Chroma** — operational simplicity. One database handles both relational metadata and vector search with ACID guarantees. Chroma loses data on restart. Pinecone adds vendor dependency and cost.
 
**Webhook → queue separation** — GitHub marks a webhook delivery as failed if it doesn't receive a response within 10 seconds. Ingestion (fetch → parse → embed → store) takes 30–60 seconds for large files. The handler drops a job into Redis and returns 200 immediately. A separate worker process handles the rest.
 
**SHA256 content hashing** — each file's hash is stored in the DB. On push, the new hash is compared with the stored one. If identical, the file is skipped entirely — zero embedding cost. Only changed files are re-processed.
 
**Hybrid retrieval** — vector search is great for semantic meaning but misses exact function names. BM25 catches exact matches but misses synonyms. Reciprocal Rank Fusion merges both ranked lists and consistently outperforms either alone.
 
---
 
## Project Structure
 
```
devpulse/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
│
├── app/
│   ├── main.py                     # FastAPI app, routers, startup warmup
│   ├── config.py                   # Pydantic settings, reads from .env
│   │
│   ├── ingestion/
│   │   ├── ast_chunker.py          # tree-sitter: .py file → chunks with line numbers
│   │   ├── embedder.py             # BGE model singleton, embed_chunks(), embed_query()
│   │   └── indexer.py              # ingest_file(), ingest_folder(), SHA256 hash check
│   │
│   ├── retrieval/
│   │   ├── vector_store.py         # pgvector: bulk_insert, search, delete_by_file
│   │   ├── hybrid.py               # RRF fusion, keyword filter, hybrid_search()
│   │   └── reranker.py             # BGE reranker (Phase 5)
│   │
│   ├── generation/
│   │   └── llm.py                  # stream_answer(), Groq primary + Gemini fallback
│   │
│   ├── api/
│   │   ├── routes_query.py         # POST /query — REST endpoint
│   │   ├── routes_webhook.py       # POST /webhook/github — HMAC validate + enqueue
│   │   ├── routes_ws.py            # WS /ws/{repo_id} — streaming query + index progress
│   │   └── connection_manager.py   # WebSocket registry + Redis pub/sub broadcast
│   │
│   ├── workers/
│   │   └── ingestion_worker.py     # Dramatiq actor: process_push_event()
│   │
│   └── db/
│       ├── models.py               # SQLAlchemy: Repo, File, Chunk
│       ├── session.py              # async engine, get_session() dependency
│       └── migrations/             # Alembic migrations
│
└── eval/
    ├── golden_dataset.json         # 20 questions with ground truth answers
    ├── run_eval.py                 # RAGAs scoring pipeline
    └── results.json                # latest eval scores
```
 
---
 
## Database Schema
 
```sql
-- repos: tracks connected GitHub repos
CREATE TABLE repos (
    id          VARCHAR(22) PRIMARY KEY,   -- shortuuid
    github_url  TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',    -- pending | indexing | indexed | error
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
 
-- files: one row per indexed file, stores hash for change detection
CREATE TABLE files (
    id              VARCHAR(22) PRIMARY KEY,
    repo_id         VARCHAR(22) REFERENCES repos(id),
    file_path       TEXT NOT NULL,
    file_hash       TEXT NOT NULL,          -- SHA256, used to skip unchanged files
    last_indexed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(repo_id, file_path)
);
 
-- chunks: the vector store
CREATE TABLE chunks (
    id            VARCHAR(22) PRIMARY KEY,
    repo_id       VARCHAR(22) REFERENCES repos(id),
    file_path     TEXT NOT NULL,
    function_name TEXT,
    start_line    INT,
    end_line      INT,
    raw_text      TEXT NOT NULL,
    embedding     vector(768),              -- BGE-base produces 768-dim vectors
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
 
CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```
 
---
 
## Getting Started
 
### Prerequisites
 
- Docker and Docker Compose
- A GitHub repo to index
- [Groq API key](https://console.groq.com) (free, no credit card)
- ngrok (for local webhook testing)
 
### Setup
 
**1. Clone and configure**
 
```bash
git clone https://github.com/J-Krishhna/devpulse
cd devpulse
cp .env.example .env
# fill in GROQ_API_KEY and GITHUB_WEBHOOK_SECRET in .env
```
 
**2. Start databases**
 
```bash
docker-compose up -d postgres redis
```
 
**3. Run migrations**
 
```bash
pip install -r requirements.txt
alembic upgrade head
docker exec -it devpulse-postgres-1 psql -U devpulse -d devpulse \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```
 
**4. Start the full stack**
 
```bash
docker-compose up --build
```
 
**5. Connect a repo**
 
```bash
# Create a repo record and trigger initial indexing
python scripts/seed_index.py
```
 
**6. Register GitHub webhook**
 
```bash
ngrok http 8000
# Set webhook URL to: https://<ngrok-id>.ngrok-free.app/webhook/github
# Content type: application/json
# Secret: matches GITHUB_WEBHOOK_SECRET in .env
# Event: push only
```
 
**7. Open the UI**
 
```
http://localhost:8000/static/index.html
```
 
Paste your `repo_id` into the `REPO_ID` field in the HTML and start asking questions.
 
---
 
## API
 
### `POST /query`
 
REST query endpoint. Returns a streaming plain-text response.
 
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"repo_id": "<repo_id>", "question": "how does authentication work?"}' \
  --no-buffer
```
 
### `WS /ws/{repo_id}`
 
WebSocket endpoint. Send and receive JSON messages.
 
```json
// client → server
{"type": "query", "question": "how does the embedding pipeline work?"}
 
// server → client (streaming)
{"type": "token", "content": "The "}
{"type": "token", "content": "embedding "}
{"type": "done"}
 
// server → client (index progress, on push)
{"type": "index_progress", "message": "Re-indexed 3 file(s), removed 0 file(s)"}
```
 
### `POST /webhook/github`
 
Receives GitHub push events. Validates HMAC-SHA256 signature, enqueues re-index job, returns 200 immediately.
 
---
 
## Running Evals
 
```bash
# First run — queries DevPulse and caches results
python eval/run_eval.py
 
# Subsequent runs — uses cache, only re-scores (no Groq calls for queries)
python eval/run_eval.py
 
# To re-run queries from scratch
rm eval/query_cache.json
python eval/run_eval.py
