from datetime import UTC, datetime

from worker import celery_app


@celery_app.task(name="pocket_maintainer.health.ping")
def ping(message: str = "pong") -> dict[str, str]:
    return {
        "status": "ok",
        "message": message,
        "worker_time": datetime.now(UTC).isoformat(),
    }
