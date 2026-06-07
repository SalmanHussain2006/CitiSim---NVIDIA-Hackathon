"""
nemotron_client.py - one local Nemotron client for the whole system.

Nemotron is NVIDIA's open reasoning LLM. On the DGX Spark you serve it LOCALLY
(Ollama, a NIM container, vLLM or llama.cpp) - every one of those exposes an
OpenAI-compatible API, so this single client works against any of them: you only
change the base URL and the model name.

Running it locally (NOT the hosted build.nvidia.com API) is the whole point for
the bounty: it's what earns the "Spark Story" points and keeps City data private.

Config via environment (defaults assume the NemoClaw/Ollama local setup):
    NEMOTRON_BASE_URL   default http://localhost:11434/v1   (NIM: http://localhost:8000/v1)
    NEMOTRON_MODEL      default nemotron-3-nano:30b          (must match what you actually serve)
    NEMOTRON_API_KEY    default "local"  (local servers ignore it; the hosted API needs a real key)

Needs only `requests`.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("NEMOTRON_BASE_URL", "http://localhost:11434/v1")
MODEL = os.environ.get("NEMOTRON_MODEL", "nemotron-3-nano:30b")
API_KEY = os.environ.get("NEMOTRON_API_KEY", "local")


class NemotronError(RuntimeError):
    """Raised when the local Nemotron server is unreachable or returns bad output."""


def _headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def health() -> bool:
    """True if a local Nemotron server is reachable. Call this before relying on it."""
    try:
        response = requests.get(f"{BASE_URL}/models", headers=_headers(), timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def chat(
    messages: list[dict],
    temperature: float = 0.6,
    top_p: float = 0.95,
    max_tokens: int = 1024,
    model: Optional[str] = None,
    timeout: int = 120,
) -> str:
    """
    Send chat messages to local Nemotron and return the reply text.

    Defaults (temperature 0.6 / top_p 0.95) follow NVIDIA's recommendation for
    tool-calling and structured output; bump temperature toward 1.0 for free chat.
    """
    payload = {
        "model": model or MODEL,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }
    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=_headers(),
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise NemotronError(
            f"Nemotron request failed against {BASE_URL}. Is the local server running? ({error})"
        ) from error

    return response.json()["choices"][0]["message"]["content"]


def reason(system_prompt: str, user_prompt: str, **kwargs) -> str:
    """Convenience for a single system + user turn."""
    return chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        **kwargs,
    )


def reason_json(system_prompt: str, user_prompt: str, **kwargs) -> Any:
    """
    Ask Nemotron for JSON and parse it. We force JSON-only and strip any code
    fences first, since small local models sometimes wrap output in ```.
    """
    system = system_prompt + "\n\nRespond with valid JSON only. No prose, no code fences."
    text = reason(system, user_prompt, **kwargs)
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise NemotronError(f"Nemotron did not return valid JSON:\n{text}") from error


if __name__ == "__main__":
    # Smoke test against your local server:  python nemotron_client.py
    print(f"base_url = {BASE_URL}")
    print(f"model    = {MODEL}")
    if not health():
        print("No local Nemotron server reachable. Start Ollama or a NIM container first (see header).")
        raise SystemExit(1)
    reply = reason(
        "You are a concise city operations analyst.",
        "In one sentence, why might roadworks and a congestion spike at the same junction be related?",
    )
    print("Nemotron says:", reply)
