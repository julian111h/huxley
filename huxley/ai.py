"""Thin client for a local OpenAI-compatible endpoint (Ollama, llama.cpp server, etc).

Never talks to anything but the user-configured base_url — no cloud fallback.
"""

import json
from collections.abc import AsyncIterator

import httpx

TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
STREAM_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

# Tunable in code (no UI for these — ghost text is meant to be fast and
# unobtrusive, not configurable per-request). num_predict/repeat_penalty are
# Ollama's native option names; sent as best-effort extras since the rest of
# this client targets the generic OpenAI-compatible surface.
GHOST_GENERATION_SETTINGS = {
    "temperature": 0.25,
    "top_p": 0.9,
    "num_predict": 24,
    "repeat_penalty": 1.05,
}

GHOST_SYSTEM_PROMPT = """You are an autocomplete engine.

Predict only the text that naturally comes next.

Rules:
Continue the current sentence if it is unfinished.
Match the author's style.
Never explain.
Never answer questions.
Never wrap the completion in markdown.
Output ONLY the continuation.
Stop naturally after roughly one sentence."""


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


async def stream_ghost_completion(base_url: str, model: str, prompt: str) -> AsyncIterator[str]:
    """Streams raw completion text as it's generated, for ghost-text display.

    Reasoning models (e.g. gpt-oss) may burn part or all of num_predict's
    tiny budget on a hidden reasoning pass and yield nothing — `think: false`
    below is sent as a best-effort hint but isn't honored by every model
    (confirmed empirically: gpt-oss ignores it entirely). Point
    autocomplete_model at a genuinely non-reasoning model (e.g. llama3.1,
    qwen3 in non-thinking mode) instead of relying on this flag.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": GHOST_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "temperature": GHOST_GENERATION_SETTINGS["temperature"],
        "top_p": GHOST_GENERATION_SETTINGS["top_p"],
        "max_tokens": GHOST_GENERATION_SETTINGS["num_predict"],
        "repeat_penalty": GHOST_GENERATION_SETTINGS["repeat_penalty"],
        "think": False,
    }
    async with httpx.AsyncClient(timeout=STREAM_TIMEOUT) as client:
        async with client.stream("POST", f"{base_url.rstrip('/')}/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[len("data: ") :]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    yield delta


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
