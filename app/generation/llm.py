from groq import AsyncGroq
from app.config import settings
import httpx

_groq_client = AsyncGroq(api_key=settings.groq_api_key)


def _build_prompt(query: str, chunks: list[dict]) -> str:
    """
    Assemble the context block from retrieved chunks.
    Each chunk gets a header showing its source location —
    this is what produces citations in the answer.
    """
    context_parts = []
    for i, chunk in enumerate(chunks):
        header = f"[{i+1}] {chunk['file_path']} — {chunk['function_name']} (lines {chunk['start_line']}–{chunk['end_line']})"
        context_parts.append(f"{header}\n{chunk['raw_text']}")

    context = "\n\n---\n\n".join(context_parts)

    return f"""You are a codebase assistant. Answer the developer's question using only the code context provided below.
For each claim you make, cite the source using its [number].
If the context doesn't contain enough information to answer, say so clearly — do not guess.

CONTEXT:
{context}

QUESTION:
{query}

ANSWER:"""


async def stream_answer(query: str, chunks: list[dict]):
    """
    Stream an answer from Groq token by token.
    This is an async generator — callers iterate over it with `async for token in stream_answer(...)`.
    Groq primary, Gemini fallback if Groq rate-limits.
    """
    prompt = _build_prompt(query, chunks)

    try:
        stream = await _groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            stream=True,
        )

        async for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token

    except Exception as e:
        # Groq failed — fall back to Gemini
        if "rate" in str(e).lower() or "429" in str(e):
            async for token in _gemini_fallback(prompt):
                yield token
        else:
            raise


async def _gemini_fallback(prompt: str):
    """
    Gemini 2.0 Flash via Google AI Studio.
    Same OpenAI-compatible interface, different base URL.
    """
    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    payload = {
        "model": "gemini-2.5-flash-lite",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "stream": True,
    }

    headers = {
        "Authorization": f"Bearer {settings.gemini_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    import json
                    parsed = json.loads(data)
                    token = parsed["choices"][0]["delta"].get("content")
                    if token:
                        yield token
                except Exception:
                    continue