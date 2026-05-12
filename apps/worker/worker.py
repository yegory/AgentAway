import os

from celery import Celery


redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "pocket_maintainer_worker",
    broker=redis_url,
    backend=redis_url,
    include=[
        "tasks.health",
        "tasks.handle_webhook",
        "tasks.create_plan",
        "tasks.implement_patch",
    ],
)

celery_app.conf.update(
    accept_content=["json"],
    result_expires=3600,
    result_serializer="json",
    task_serializer="json",
    task_track_started=True,
)
