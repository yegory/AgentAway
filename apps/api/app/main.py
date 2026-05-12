from typing import Any

import anyio
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.celery_app import celery_app
from app.config import cors_origins, settings, validate_production_settings
from app.db import check_postgres, check_redis, create_tables
from app.routes import api_v1, auth, auth_tokens, github, provider_keys, runs, webhooks, workbench


app = FastAPI(title="Pocket Maintainer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhooks.router)
app.include_router(auth.router)
app.include_router(auth_tokens.router)
app.include_router(api_v1.router)
app.include_router(provider_keys.router)
app.include_router(github.router)
app.include_router(github.installations_router)
app.include_router(runs.router)
app.include_router(workbench.router)


@app.on_event("startup")
async def on_startup() -> None:
    validate_production_settings()
    await anyio.to_thread.run_sync(create_tables)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


@app.get("/health")
async def health() -> dict[str, Any]:
    dependencies: dict[str, str] = {}

    try:
        await anyio.to_thread.run_sync(check_postgres)
        dependencies["postgres"] = "ok"
    except Exception as exc:  # pragma: no cover - exercised by runtime checks
        dependencies["postgres"] = f"error: {exc}"

    try:
        await check_redis()
        dependencies["redis"] = "ok"
    except Exception as exc:  # pragma: no cover - exercised by runtime checks
        dependencies["redis"] = f"error: {exc}"

    if any(value != "ok" for value in dependencies.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "dependencies": dependencies},
        )

    return {"status": "ok", "service": "api", "dependencies": dependencies}


@app.post("/tasks/ping", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_ping() -> dict[str, str]:
    result = celery_app.send_task("pocket_maintainer.health.ping", kwargs={"message": "pong"})
    return {"task_id": result.id, "status_url": f"/tasks/{result.id}"}


@app.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    result = celery_app.AsyncResult(task_id)
    body: dict[str, Any] = {"task_id": task_id, "state": result.state}

    if result.ready():
        value = result.get(timeout=1, propagate=False)
        if result.failed():
            body["error"] = str(value)
        else:
            body["result"] = value

    return body
