from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import sys
import os
import numpy as np

sys.path.append(".")
from openai import OpenAI

# ── 1. FIXED: Standard Ragas 0.4.x Imports ──
from ragas import evaluate
from ragas.metrics import (
    Faithfulness,
    AnswerRelevancy,
    LLMContextPrecisionWithReference,
    LLMContextRecall
)
from ragas.llms import llm_factory
from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
from ragas.run_config import RunConfig
# ── 2. FIXED: Robust Local Embeddings ──
from langchain_huggingface import HuggingFaceEmbeddings
from ragas.embeddings import LangchainEmbeddingsWrapper

from groq import Groq
from app.db.session import async_session
from app.retrieval.hybrid import hybrid_search
from app.generation.llm import stream_answer

REPO_ID = "o7V2qSaJnLiyaCXb76NhTt"
CACHE_FILE = "eval/query_cache.json"

async def run_query(question: str) -> tuple[str, list[str]]:
    async with async_session() as session:
        chunks = await hybrid_search(session, question, REPO_ID)

    answer_tokens = []
    async for token in stream_answer(question, chunks):
        answer_tokens.append(token)

    answer = "".join(answer_tokens)
    contexts = [c["raw_text"] for c in chunks]
    return answer, contexts

async def build_query_cache(golden_dataset: list[dict]) -> list[dict]:
    if os.path.exists(CACHE_FILE):
        print(f"✅ Cache found at {CACHE_FILE} — skipping query phase")
        with open(CACHE_FILE) as f:
            return json.load(f)

    print("No cache found — running queries (this calls Groq once per question)")
    results = []

    for i, item in enumerate(golden_dataset):
        print(f"  {i+1}/{len(golden_dataset)}: {item['question'][:60]}...")
        try:
            answer, contexts = await run_query(item["question"])
            results.append({
                "question": item["question"],
                "answer": answer,
                "contexts": contexts,
                "ground_truth": item["ground_truth"],
            })
            print(f"    ✅ {len(answer)} chars, {len(contexts)} chunks")
        except Exception as e:
            print(f"    ❌ failed: {e}")

    os.makedirs("eval", exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Query results cached to {CACHE_FILE}")

    return results

async def main():
    with open("eval/golden_dataset.json") as f:
        golden_dataset = json.load(f)
    print(f"Loaded {len(golden_dataset)} questions\n")

    print("── Phase 1: Query pipeline ──────────────────────────────────────")
    cached = await build_query_cache(golden_dataset)
    print(f"   {len(cached)} questions ready for scoring\n")

    print("── Phase 2: Build RAGAs dataset ─────────────────────────────────")
    samples = [
        SingleTurnSample(
            user_input=item["question"],
            response=item["answer"],
            retrieved_contexts=item["contexts"],
            reference=item["ground_truth"],
        )
        for item in cached
    ]
    dataset = EvaluationDataset(samples=samples)

    print("── Phase 3: Scoring with RAGAs ──────────────────────────────────")

    groq_openai_client = OpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )

    # ── 3. FIXED: Explicit provider mapping for Groq ──
    evaluator_llm = llm_factory(
        "llama-3.3-70b-versatile",
        provider="openai", 
        client=groq_openai_client,
    )

    # ── 4. FIXED: Wrap local HuggingFace embeddings safely ──
    evaluator_embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="BAAI/bge-base-en-v1.5")
    )

    custom_config = RunConfig(
        max_workers=2, 
        max_retries=3,
        max_wait=10 # wait up to 10 seconds between retries
    )

    # ── 5. FIXED: Instantiate the new Metric Objects ──
    result = evaluate(
        dataset=dataset,
        metrics=[
            Faithfulness(),
            AnswerRelevancy(),
            LLMContextPrecisionWithReference(),
            LLMContextRecall(),
        ],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        run_config=custom_config # Pass the throttle here!
    )

    df = result.to_pandas()

    def safe_mean(col):
        if col in df.columns:
            return float(df[col].dropna().mean())
        return None

    faith  = safe_mean("faithfulness")
    rel    = safe_mean("answer_relevancy")
    prec   = safe_mean("llm_context_precision_with_reference")
    recall = safe_mean("context_recall")

    print("\n══════════════════════════════════════════════════")
    print("  DevPulse RAGAs Evaluation Report")
    print("══════════════════════════════════════════════════")
    print(f"  Questions evaluated:  {len(cached)}")
    print(f"  Faithfulness:         {faith:.4f}" if faith else "  Faithfulness:         N/A")
    print(f"  Answer Relevancy:     {rel:.4f}" if rel else "  Answer Relevancy:     N/A")
    print(f"  Context Precision:    {prec:.4f}" if prec else "  Context Precision:    N/A")
    print(f"  Context Recall:       {recall:.4f}" if recall else "  Context Recall:       N/A")
    print("══════════════════════════════════════════════════")

    result_dict = {k: v for k, v in {
        "faithfulness": faith,
        "answer_relevancy": rel,
        "context_precision": prec,
        "context_recall": recall,
        "num_questions": len(cached),
    }.items() if v is not None}

    with open("eval/results.json", "w") as f:
        json.dump(result_dict, f, indent=2)
    print("\n  Results saved to eval/results.json")
    print(f"  Query cache at {CACHE_FILE} — delete it to re-run queries\n")


asyncio.run(main())