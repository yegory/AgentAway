from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import settings


VALID_PROVIDERS = {"openai", "anthropic", "deepseek"}


@dataclass(frozen=True)
class ProviderDefaults:
    model_name: str
    base_url: str


def provider_defaults(provider: str) -> ProviderDefaults:
    defaults = {
        "openai": ProviderDefaults(settings.default_openai_model, "https://api.openai.com"),
        "anthropic": ProviderDefaults(settings.default_anthropic_model, "https://api.anthropic.com"),
        "deepseek": ProviderDefaults(settings.default_deepseek_model, settings.deepseek_base_url),
    }
    return defaults[provider]


def normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in VALID_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    return normalized


async def test_provider_key(provider: str, api_key: str, base_url: str) -> dict[str, str]:
    provider = normalize_provider(provider)
    base = base_url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if provider in {"openai", "deepseek"}:
                response = await client.get(
                    f"{base}/v1/models" if provider == "openai" else f"{base}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            else:
                response = await client.get(
                    f"{base}/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
    except httpx.HTTPError as exc:
        return {"status": "error", "message": str(exc)}

    if response.status_code < 400:
        return {"status": "ok", "message": "Provider key accepted."}

    if response.status_code in {401, 403}:
        return {"status": "error", "message": "Provider rejected the API key."}

    return {
        "status": "warning",
        "message": f"Provider returned HTTP {response.status_code}; key was stored but could not be fully verified.",
    }
