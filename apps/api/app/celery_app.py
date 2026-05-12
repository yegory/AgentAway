from celery import Celery

from app.config import settings


celery_app = Celery(
    "pocket_maintainer_api",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    accept_content=["json"],
    result_expires=3600,
    result_serializer="json",
    task_serializer="json",
)
