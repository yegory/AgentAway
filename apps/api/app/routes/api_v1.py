from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AgentRun, RunEvent
from app.routes import runs, workbench
from app.services.audit_log import record_audit
from app.services.auth import AuthenticatedUser, require_scopes
from app.services.rate_limits import check_rate_limit


router = APIRouter(prefix="/api/v1", tags=["api-v1"])


def ensure_scope(current_user: AuthenticatedUser, scope: str) -> None:
    if not current_user.has_scope(scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required scope: {scope}",
        )


def serialize_principal(current_user: AuthenticatedUser) -> dict[str, object]:
    account = current_user.account
    return {
        "user": {
            "id": account.id,
            "email": account.email,
            "display_name": account.display_name,
            "default_provider": account.default_provider,
        },
        "auth": {
            "method": current_user.auth_method,
            "scopes": sorted(current_user.scopes),
            "token_family_id": current_user.token_family_id,
        },
    }


@router.get("/me")
def me(
    current_user: AuthenticatedUser = Depends(require_scopes("account:read")),
) -> dict[str, object]:
    return serialize_principal(current_user)


@router.get("/repositories")
def list_repositories(
    current_user: AuthenticatedUser = Depends(require_scopes("repos:read")),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    sync_errors = workbench.sync_repositories_for_user(session, current_user.account)
    repositories = workbench.get_accessible_repositories(session, current_user.account.id)
    return {
        "repositories": [workbench.serialize_repository(repository) for repository in repositories],
        "sync_errors": sync_errors,
    }


@router.get("/repositories/{repository_id}/issues")
def list_issues(
    repository_id: int,
    state: str = Query(default="open", pattern="^(open|closed|all)$"),
    current_user: AuthenticatedUser = Depends(require_scopes("issues:read")),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repository = workbench.require_repository_access(session, current_user, repository_id)
    token = workbench.installation_token_for_repository(repository)
    try:
        issues = workbench.github_client.list_issues(token, repository.full_name, state)
    except httpx.HTTPStatusError as exc:
        raise workbench.github_error(exc) from exc
    return {"issues": [workbench.serialize_issue(issue) for issue in issues]}


@router.post("/repositories/{repository_id}/issues", status_code=status.HTTP_201_CREATED)
def create_issue(
    repository_id: int,
    body: workbench.IssueCreateRequest,
    current_user: AuthenticatedUser = Depends(require_scopes("issues:write")),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    has_command = body.first_command != "none" or bool(body.raw_command and body.raw_command.strip())
    if has_command:
        ensure_scope(current_user, "commands:write")

    repository = workbench.require_repository_access(session, current_user, repository_id)
    token = workbench.installation_token_for_repository(repository)
    try:
        issue = workbench.github_client.create_issue(token, repository.full_name, body.title.strip(), body.body)
        command_comment = None
        parsed_command = None
        run = None
        run_task_id = None
        if has_command:
            constraints = body.constraints
            if not constraints and body.first_command in {"plan", "fix"} and not body.raw_command:
                constraints = ["add tests", "max 2 files"]
            command_text, parsed_command = workbench.build_command_text(
                workbench.CommandCommentRequest(
                    command=body.first_command,
                    constraints=constraints,
                    raw_command=body.raw_command,
                    confirm_implementation=body.confirm_implementation,
                )
            )
            command_comment = workbench.github_client.create_issue_comment(
                token,
                repository.full_name,
                int(issue["number"]),
                command_text,
            )
            run = workbench.create_authorized_command_run(
                session,
                current_user=current_user,
                repository=repository,
                issue=issue,
                comment=command_comment,
                parsed=parsed_command,
                trigger_type="api_v1_command",
            )
            record_audit(
                session,
                user_id=current_user.account.id,
                action="api_v1.command_posted",
                target_type="repository",
                target_id=str(repository.id),
                payload={
                    "issue_number": issue.get("number"),
                    "command": parsed_command.command,
                    "agent_run_id": run.id,
                },
            )
            session.commit()
            run_task_id = workbench.enqueue_agent_run(run)
        return {
            "issue": workbench.serialize_issue(issue),
            "command_comment": workbench.serialize_comment(command_comment) if command_comment else None,
            "command": parsed_command.to_dict() if parsed_command else None,
            "agent_run_id": run.id if run else None,
            "run_task_id": run_task_id,
        }
    except httpx.HTTPStatusError as exc:
        raise workbench.github_error(exc) from exc


@router.post("/repositories/{repository_id}/issues/{issue_number}/comments", status_code=status.HTTP_201_CREATED)
def create_comment(
    repository_id: int,
    issue_number: int,
    body: workbench.CommentCreateRequest,
    current_user: AuthenticatedUser = Depends(require_scopes("issues:write")),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repository = workbench.require_repository_access(session, current_user, repository_id)
    token = workbench.installation_token_for_repository(repository)
    try:
        comment = workbench.github_client.create_issue_comment(token, repository.full_name, issue_number, body.body)
    except httpx.HTTPStatusError as exc:
        raise workbench.github_error(exc) from exc
    record_audit(
        session,
        user_id=current_user.account.id,
        action="api_v1.issue_comment_created",
        target_type="repository",
        target_id=str(repository.id),
        payload={"issue_number": issue_number},
    )
    session.commit()
    return {"comment": workbench.serialize_comment(comment)}


@router.post("/repositories/{repository_id}/issues/{issue_number}/commands", status_code=status.HTTP_201_CREATED)
def create_command(
    repository_id: int,
    issue_number: int,
    body: workbench.CommandCommentRequest,
    current_user: AuthenticatedUser = Depends(require_scopes("commands:write")),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repository = workbench.require_repository_access(session, current_user, repository_id)
    command_text, parsed = workbench.build_command_text(body)
    if parsed.command in workbench.HIGH_RISK_COMMANDS:
        check_rate_limit(f"high-risk-command:{current_user.account.id}", limit=20)
    token = workbench.installation_token_for_repository(repository)
    try:
        issue = workbench.github_client.get_issue(token, repository.full_name, issue_number)
        comment = workbench.github_client.create_issue_comment(token, repository.full_name, issue_number, command_text)
    except httpx.HTTPStatusError as exc:
        raise workbench.github_error(exc) from exc
    run = workbench.create_authorized_command_run(
        session,
        current_user=current_user,
        repository=repository,
        issue=issue,
        comment=comment,
        parsed=parsed,
        trigger_type="api_v1_command",
    )
    record_audit(
        session,
        user_id=current_user.account.id,
        action="api_v1.command_posted",
        target_type="repository",
        target_id=str(repository.id),
        payload={"issue_number": issue_number, "command": parsed.command, "agent_run_id": run.id},
    )
    session.commit()
    run_task_id = workbench.enqueue_agent_run(run)
    return {
        "status": "comment_posted",
        "comment": workbench.serialize_comment(comment),
        "command": parsed.to_dict(),
        "agent_run_id": run.id,
        "run_task_id": run_task_id,
    }


@router.get("/runs")
def list_runs(
    current_user: AuthenticatedUser = Depends(require_scopes("runs:read")),
    session: Session = Depends(get_session),
) -> dict[str, list[dict[str, Any]]]:
    ownership_filter = AgentRun.user_id == current_user.account.id
    if current_user.is_dev:
        ownership_filter = or_(ownership_filter, AgentRun.user_id.is_(None))
    agent_runs = session.scalars(
        select(AgentRun)
        .where(ownership_filter)
        .order_by(desc(AgentRun.created_at))
        .limit(50)
    ).all()
    return {"runs": [runs.serialize_run(run) for run in agent_runs]}


@router.get("/runs/{run_id}")
def get_run(
    run_id: int,
    current_user: AuthenticatedUser = Depends(require_scopes("runs:read")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = runs.require_visible_run(run_id, current_user, session)
    events = session.scalars(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.created_at)
    ).all()
    body = runs.serialize_run(run)
    body["events"] = [
        {
            "id": event.id,
            "event_type": event.event_type,
            "message": runs.redact_text(event.message),
            "payload_json": runs.redact_json(event.payload_json),
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]
    return body


@router.post("/runs/{run_id}/stop")
def stop_run(
    run_id: int,
    current_user: AuthenticatedUser = Depends(require_scopes("runs:write")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = runs.require_visible_run(run_id, current_user, session)
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
            message="Stop was requested from the API.",
            payload_json={"auth_method": current_user.auth_method},
        )
    )
    record_audit(
        session,
        user_id=current_user.account.id,
        action="api_v1.run_stop_requested",
        target_type="agent_run",
        target_id=str(run.id),
        payload={},
    )
    session.commit()
    session.refresh(run)
    return {"run": runs.serialize_run(run)}
