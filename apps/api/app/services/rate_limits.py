from __future__ import annotations

from functools import lru_cache

import redis
from fastapi import HTTPException, status

from app.config import settings


@lru_cache(maxsize=1)
def redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)


def check_rate_limit(key: str, *, limit: int | None = None, window_seconds: int = 60) -> None:
    effective_limit = max(1, int(limit or settings.api_rate_limit_per_minute))
    redis_key = f"rate:{key}"
    try:
        client = redis_client()
        count = int(client.incr(redis_key))
        if count == 1:
            client.expire(redis_key, window_seconds)
    except Exception:
        if settings.app_env == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limit service is unavailable.",
            )
        return

    if count > effective_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded.",
        )
