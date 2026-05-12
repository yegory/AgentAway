from typing import Any
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AgentRun, RunEvent
from app.services.audit_log import record_audit
from app.services.auth import AuthenticatedUser, get_current_user


router = APIRouter(prefix="/api/runs", tags=["runs"])


SECRET_PATTERNS = [
    (re.compile(r"https://x-access-token:[^@]+@github\.com/"), "https://x-access-token:<redacted>@github.com/"),
    (re.compile(r"\bgh[spuor]_[A-Za-z0-9_]+\b"), "<redacted>"),
    (re.compile(r"\b(sk|sk-ant|sk-or)-[A-Za-z0-9_-]{16,}\b"), "<redacted>"),
]


def redact_text(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = value
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_json(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            if any(secret_word in key.lower() for secret_word in ("token", "secret", "key", "password")):
                safe[key] = "<redacted>"
            else:
                safe[key] = redact_json(item)
        return safe
    return value


def serialize_run(run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "user_id": run.user_id,
        "repository_id": run.repository_id,
        "repository": {
            "id": run.repository.id,
            "full_name": run.repository.full_name,
            "default_branch": run.repository.default_branch,
        }
        if run.repository
        else None,
        "issue_number": run.issue_number,
        "issue_title": run.issue_title,
        "issue_url": run.issue_url,
        "comment_url": run.comment_url,
        "pull_request_number": run.pull_request_number,
        "pull_request_url": run.pull_request_url,
        "github_delivery_id": run.github_delivery_id,
        "trigger_type": run.trigger_type,
        "trigger_actor": run.trigger_actor,
        "command": run.command,
        "status": run.status,
        "provider": run.provider,
        "model_name": run.model_name,
        "risk_level": run.risk_level,
        "confidence": run.confidence,
        "branch_name": run.branch_name,
        "base_sha": run.base_sha,
        "head_sha": run.head_sha,
        "plan_json": redact_json(run.plan_json),
        "diff_summary_json": redact_json(run.diff_summary_json),
        "test_summary_json": redact_json(run.test_summary_json),
        "review_summary_json": redact_json(run.review_summary_json),
        "error_message": redact_text(run.error_message),
        "cancellation_requested": run.cancellation_requested,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def require_visible_run(
    run_id: int,
    current_user: AuthenticatedUser,
    session: Session,
) -> AgentRun:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")

    if run.user_id not in {current_user.account.id, None} or (run.user_id is None and not current_user.is_dev):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")

    return run


@router.get("")
def list_runs(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, list[dict[str, Any]]]:
    ownership_filter = AgentRun.user_id == current_user.account.id
    if current_user.is_dev:
        ownership_filter = or_(ownership_filter, AgentRun.user_id.is_(None))

    runs = session.scalars(
        select(AgentRun)
        .where(ownership_filter)
        .order_by(desc(AgentRun.created_at))
        .limit(50)
    ).all()
    return {"runs": [serialize_run(run) for run in runs]}


@router.get("/{run_id}")
def get_run(
    run_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = require_visible_run(run_id, current_user, session)

    events = session.scalars(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.created_at)
    ).all()
    body = serialize_run(run)
    body["events"] = [
        {
            "id": event.id,
            "event_type": event.event_type,
            "message": redact_text(event.message),
            "payload_json": redact_json(event.payload_json),
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]
    return body


@router.post("/{run_id}/stop")
def request_stop(
    run_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = require_visible_run(run_id, current_user, session)
    terminal_statuses = {"planned", "failed", "draft_pr_opened", "needs_plan", "needs_provider_key", "unauthorized_actor"}
    if run.status in terminal_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This run is not currently stoppable.",
        )

    run.cancellation_requested = True
    run.status = "stop_requested"
    session.add(
        RunEvent(
            run_id=run.id,
            event_type="stop_requested",
            message="Stop was requested from the web workbench.",
            payload_json={},
        )
    )
    record_audit(
        session,
        user_id=current_user.account.id,
        action="run.stop_requested",
        target_type="agent_run",
        target_id=str(run.id),
        payload={},
    )
    session.commit()
    session.refresh(run)
    return {"run": serialize_run(run)}
