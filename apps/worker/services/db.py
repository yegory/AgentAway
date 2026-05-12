from __future__ import annotations

import json
from typing import Any

from sqlalchemy import create_engine, text

from services import settings


engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)


def json_param(value: Any) -> str:
    return json.dumps(value or {})


def add_run_event(connection: Any, run_id: int, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
    connection.execute(
        text(
            """
            INSERT INTO run_events (run_id, event_type, message, payload_json, created_at)
            VALUES (:run_id, :event_type, :message, CAST(:payload_json AS jsonb), NOW())
            """
        ),
        {
            "run_id": run_id,
            "event_type": event_type,
            "message": message,
            "payload_json": json_param(payload),
        },
    )


def update_run(connection: Any, run_id: int, **fields: Any) -> None:
    assignments: list[str] = []
    params: dict[str, Any] = {"run_id": run_id}
    json_fields = {"plan_json", "diff_summary_json", "test_summary_json", "review_summary_json"}

    for name, value in fields.items():
        if name in json_fields:
            assignments.append(f"{name} = CAST(:{name} AS jsonb)")
            params[name] = json_param(value)
        else:
            assignments.append(f"{name} = :{name}")
            params[name] = value

    assignments.append("updated_at = NOW()")
    connection.execute(
        text(f"UPDATE agent_runs SET {', '.join(assignments)} WHERE id = :run_id"),
        params,
    )


def load_run(connection: Any, run_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        text(
            """
            SELECT
                ar.*,
                r.full_name,
                r.default_branch,
                r.private AS repo_private,
                gi.github_installation_id,
                we.payload_json AS webhook_payload
            FROM agent_runs ar
            LEFT JOIN repositories r ON r.id = ar.repository_id
            LEFT JOIN github_installations gi ON gi.id = r.installation_id
            LEFT JOIN webhook_events we ON we.github_delivery_id = ar.github_delivery_id
            WHERE ar.id = :run_id
            """
        ),
        {"run_id": run_id},
    ).mappings().first()
    return dict(row) if row else None


def load_latest_plan(connection: Any, run: dict[str, Any]) -> dict[str, Any] | None:
    row = connection.execute(
        text(
            """
            SELECT *
            FROM agent_runs
            WHERE repository_id = :repository_id
                AND issue_number = :issue_number
                AND command IN ('plan', 'fixplan')
                AND status = 'planned'
                AND id <> :run_id
                AND plan_json IS NOT NULL
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        ),
        {
            "repository_id": run.get("repository_id"),
            "issue_number": run.get("issue_number"),
            "run_id": run.get("id"),
        },
    ).mappings().first()
    return dict(row) if row else None


def load_provider_credential(connection: Any, user_id: int | None) -> dict[str, Any] | None:
    if user_id is None:
        return None
    row = connection.execute(
        text(
            """
            SELECT pc.*
            FROM provider_credentials pc
            JOIN user_accounts ua ON ua.id = pc.user_id
            WHERE pc.user_id = :user_id
            ORDER BY
                CASE WHEN pc.provider = ua.default_provider THEN 0 ELSE 1 END,
                pc.updated_at DESC
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    return dict(row) if row else None
