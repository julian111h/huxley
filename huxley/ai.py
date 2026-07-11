"""Thin client for a local OpenAI-compatible endpoint (Ollama, llama.cpp server, etc).

Never talks to anything but the user-configured base_url — no cloud fallback.
"""

import httpx

TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)


async def list_models(base_url: str) -> list[str]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{base_url.rstrip('/')}/models")
        resp.raise_for_status()
        data = resp.json()
    return sorted(m["id"] for m in data.get("data", []))


async def _chat(base_url: str, model: str, messages: list[dict], max_tokens: int, temperature: float) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def explain_error(base_url: str, model: str, message: str, log_excerpt: str) -> str:
    prompt = (
        "You are helping a LaTeX author understand a compile error. "
        "Explain plainly what went wrong and how to fix it. Be concise — a "
        "short paragraph, no preamble.\n\n"
        f"Error: {message}\n\nRelevant log excerpt:\n{log_excerpt[-1500:]}"
    )
    return await _chat(
        base_url, model,
        [{"role": "user", "content": prompt}],
        max_tokens=400, temperature=0.2,
    )


async def ghost_completion(base_url: str, model: str, prefix: str, suffix: str) -> str:
    prompt = (
        "Continue the LaTeX document below at the <CURSOR> marker. Output only "
        "the continuation text (a few words to one short clause) — no commentary, "
        "no markdown fences, nothing before or after.\n\n"
        f"{prefix[-1200:]}<CURSOR>{suffix[:200]}"
    )
    # max_tokens is generous because reasoning models (e.g. gpt-oss) spend part of
    # this budget on a hidden reasoning pass before emitting the actual content —
    # too small a cap truncates them to an empty answer. Non-reasoning models just
    # finish early. For snappy ghost text, point autocomplete_model at a fast
    # non-reasoning model instead (e.g. llama3.1) rather than relying on this cap.
    text = await _chat(
        base_url, model,
        [{"role": "user", "content": prompt}],
        max_tokens=300, temperature=0.1,
    )
    return text.split("\n")[0].strip()


async def improve_text(base_url: str, model: str, text: str) -> str:
    prompt = (
        "Improve the following passage from an academic/technical LaTeX document: "
        "tighten the prose and fix awkward phrasing, but keep the same meaning and "
        "length in the same ballpark. Preserve every LaTeX command "
        "(\\command{...}, math, etc.) exactly as-is. Output only the improved "
        "passage — no commentary, no markdown fences, nothing before or after.\n\n"
        f"{text}"
    )
    return await _chat(
        base_url, model,
        [{"role": "user", "content": prompt}],
        # +700 covers a reasoning model's hidden thinking pass (see ghost_completion).
        max_tokens=len(text) + 700, temperature=0.3,
    )
