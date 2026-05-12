from __future__ import annotations

import json
import re
from typing import Any

import httpx


def chat_completion(
    provider: str,
    api_key: str,
    base_url: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    provider = provider.lower()
    base = base_url.rstrip("/")

    if provider in {"openai", "deepseek"}:
        path = "/v1/chat/completions" if provider == "openai" else "/chat/completions"
        response = httpx.post(
            f"{base}{path}",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            },
            timeout=90,
        )
        response.raise_for_status()
        body = response.json()
        return body["choices"][0]["message"]["content"]

    if provider == "anthropic":
        response = httpx.post(
            f"{base}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
                "max_tokens": 4096,
                "temperature": 0.2,
            },
            timeout=90,
        )
        response.raise_for_status()
        body = response.json()
        return "\n".join(block.get("text", "") for block in body.get("content", []) if block.get("type") == "text")

    raise ValueError(f"Unsupported provider: {provider}")


def parse_json_object(text: str) -> dict[str, Any]:
    clean = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean, flags=re.DOTALL)
    if fenced:
        clean = fenced.group(1)
    else:
        start = clean.find("{")
        end = clean.rfind("}")
        if start >= 0 and end > start:
            clean = clean[start : end + 1]

    value = json.loads(clean)
    if not isinstance(value, dict):
        raise ValueError("Model response was not a JSON object.")
    return value
