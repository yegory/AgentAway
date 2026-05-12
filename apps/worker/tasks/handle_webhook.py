import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text

from worker import celery_app
from services import github_app


COMMAND_REFERENCE = """### AgentAway commands

- `/plan [constraints]`
- `/fixplan [correction]`
- `/proceed`
- `/fix [constraints]`

Constraints: `add tests`, `max 2 files`, `only touch frontend files`
"""


def database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@postgres:5432/pocket_maintainer",
    )


def load_webhook_event(connection: Any, webhook_event_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        text(
            """
            SELECT
                we.*,
                r.full_name,
                gi.github_installation_id
            FROM webhook_events we
            LEFT JOIN repositories r ON r.id = we.repository_id
            LEFT JOIN github_installations gi ON gi.id = we.installation_id
            WHERE we.id = :event_id
            """
        ),
        {"event_id": webhook_event_id},
    ).mappings().first()
    return dict(row) if row else None


def maybe_comment_command_reference(event: dict[str, Any]) -> None:
    if event.get("github_event") != "issues" or event.get("action") != "opened":
        return
    if not event.get("github_installation_id") or not event.get("full_name"):
        return

    payload = event.get("payload_json") or {}
    issue = payload.get("issue") or {}
    issue_number = issue.get("number")
    if issue_number is None:
        return

    token = github_app.installation_token(int(event["github_installation_id"])).token
    github_app.issue_comment(token, event["full_name"], int(issue_number), COMMAND_REFERENCE)


@celery_app.task(name="pocket_maintainer.webhooks.handle")
def handle_webhook(webhook_event_id: int, agent_run_id: int | None = None) -> dict[str, int | str | None]:
    engine = create_engine(database_url(), pool_pre_ping=True)
    processed_at = datetime.now(UTC)

    with engine.begin() as connection:
        event = load_webhook_event(connection, webhook_event_id)

    if event is None:
        return {
            "status": "missing",
            "webhook_event_id": webhook_event_id,
            "agent_run_id": agent_run_id,
        }

    maybe_comment_command_reference(event)

    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE webhook_events
                SET status = :status, processed_at = :processed_at
                WHERE id = :event_id
                """
            ),
            {
                "status": "processed",
                "processed_at": processed_at,
                "event_id": webhook_event_id,
            },
        )

    return {
        "status": "processed" if result.rowcount else "missing",
        "webhook_event_id": webhook_event_id,
        "agent_run_id": agent_run_id,
    }
