from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.db import get_session
from app.models import (
    AgentRun,
    GitHubInstallation,
    ProviderCredential,
    Repository,
    RepositoryAccess,
    UserAccount,
    WebhookEvent,
)
from app.services import github_client
from app.services.audit_log import record_audit
from app.services.auth import AuthenticatedUser, get_current_user
from app.services.command_parser import ParsedCommand, parse_agent_command
from app.services.rate_limits import check_rate_limit


router = APIRouter(prefix="/api", tags=["workbench"])

HIGH_RISK_COMMANDS = {"fix", "proceed"}
WORKBENCH_COMMANDS = {"plan", "fixplan", "fix", "proceed"}
RUN_TASKS = {
    "plan": "pocket_maintainer.runs.create_plan",
    "fixplan": "pocket_maintainer.runs.create_plan",
    "fix": "pocket_maintainer.runs.implement_patch",
    "proceed": "pocket_maintainer.runs.implement_patch",
}


class IssueCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    body: str = ""
    first_command: str = "none"
    constraints: list[str] = Field(default_factory=list, max_length=8)
    raw_command: str | None = None
    confirm_implementation: bool = False


class CommentCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=65536)


class CommandCommentRequest(BaseModel):
    command: str = "plan"
    constraints: list[str] = Field(default_factory=list, max_length=8)
    raw_command: str | None = None
    confirm_implementation: bool = False


def serialize_repository(repository: Repository) -> dict[str, object]:
    return {
        "id": repository.id,
        "github_repo_id": repository.github_repo_id,
        "owner": repository.owner,
        "name": repository.name,
        "full_name": repository.full_name,
        "default_branch": repository.default_branch,
        "private": repository.private,
        "installation_id": repository.installation_id,
    }


def unique_repositories(repositories: list[Repository]) -> list[Repository]:
    seen: set[str] = set()
    unique: list[Repository] = []
    for repository in repositories:
        key = repository.full_name.lower() or str(repository.github_repo_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(repository)
    return unique


def github_install_url() -> str:
    if not settings.github_app_slug:
        return ""
    return f"https://github.com/apps/{settings.github_app_slug}/installations/new"


def serialize_installation(installation: GitHubInstallation) -> dict[str, object]:
    return {
        "id": installation.id,
        "github_installation_id": installation.github_installation_id,
        "account_login": installation.account_login,
        "account_type": installation.account_type,
        "repositories": [
            serialize_repository(repository)
            for repository in unique_repositories(installation.repositories)
        ],
    }


def serialize_run_card(run: AgentRun) -> dict[str, object]:
    return {
        "id": run.id,
        "repository_id": run.repository_id,
        "repository": serialize_repository(run.repository) if run.repository else None,
        "issue_number": run.issue_number,
        "issue_title": run.issue_title,
        "issue_url": run.issue_url,
        "comment_url": run.comment_url,
        "pull_request_url": run.pull_request_url,
        "pull_request_number": run.pull_request_number,
        "command": run.command,
        "status": run.status,
        "trigger_actor": run.trigger_actor,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def serialize_github_user(user: dict[str, Any] | None) -> dict[str, object] | None:
    if not isinstance(user, dict):
        return None
    return {
        "login": user.get("login") or "",
        "avatar_url": user.get("avatar_url") or "",
        "html_url": user.get("html_url") or "",
    }


def serialize_issue(issue: dict[str, Any]) -> dict[str, object]:
    return {
        "id": issue.get("id"),
        "number": issue.get("number"),
        "title": issue.get("title") or "",
        "body": issue.get("body") or "",
        "state": issue.get("state") or "",
        "html_url": issue.get("html_url") or "",
        "comments": issue.get("comments") or 0,
        "labels": [
            {"name": label.get("name") or "", "color": label.get("color") or ""}
            for label in issue.get("labels", [])
            if isinstance(label, dict)
        ],
        "user": serialize_github_user(issue.get("user")),
        "created_at": issue.get("created_at") or "",
        "updated_at": issue.get("updated_at") or "",
    }


def serialize_comment(comment: dict[str, Any]) -> dict[str, object]:
    return {
        "id": comment.get("id"),
        "body": comment.get("body") or "",
        "html_url": comment.get("html_url") or "",
        "user": serialize_github_user(comment.get("user")),
        "created_at": comment.get("created_at") or "",
        "updated_at": comment.get("updated_at") or "",
    }


def actor_for_user(current_user: AuthenticatedUser) -> str:
    account = current_user.account
    return account.display_name or account.email or account.clerk_user_id


def create_authorized_command_run(
    session: Session,
    *,
    current_user: AuthenticatedUser,
    repository: Repository,
    issue: dict[str, Any],
    comment: dict[str, Any],
    parsed: ParsedCommand,
    trigger_type: str,
) -> AgentRun:
    delivery_id = f"{trigger_type}-{uuid4()}"
    payload = {
        "action": "created",
        "repository": {
            "id": repository.github_repo_id,
            "full_name": repository.full_name,
            "name": repository.name,
            "default_branch": repository.default_branch,
            "private": repository.private,
            "owner": {"login": repository.owner},
        },
        "issue": issue,
        "comment": comment,
        "sender": {
            "login": actor_for_user(current_user),
            "type": "AgentAwayUser",
        },
    }
    event = WebhookEvent(
        github_delivery_id=delivery_id,
        github_event=trigger_type,
        action="created",
        installation=repository.installation,
        repository=repository,
        sender_login=actor_for_user(current_user),
        payload_json=payload,
        status="processed",
    )
    session.add(event)
    run = AgentRun(
        user=current_user.account,
        repository=repository,
        issue_number=issue.get("number"),
        issue_title=issue.get("title") or "",
        issue_url=issue.get("html_url") or "",
        comment_url=comment.get("html_url") or "",
        github_delivery_id=delivery_id,
        trigger_type=trigger_type,
        trigger_actor=actor_for_user(current_user),
        command=parsed.command,
        status=f"queued_{parsed.command}",
        plan_json={
            "command": parsed.to_dict(),
            "author_association": "WORKBENCH",
            "github_comment_url": comment.get("html_url") or "",
        },
    )
    session.add(run)
    session.flush()
    return run


def enqueue_agent_run(run: AgentRun) -> str | None:
    task_name = RUN_TASKS.get(run.command)
    if not task_name:
        return None
    result = celery_app.send_task(task_name, kwargs={"agent_run_id": run.id})
    return result.id


def github_error(exc: httpx.HTTPStatusError) -> HTTPException:
    detail = "GitHub request failed."
    try:
        body = exc.response.json()
        if isinstance(body, dict) and body.get("message"):
            detail = str(body["message"])
    except ValueError:
        pass
    return HTTPException(status_code=exc.response.status_code, detail=detail)


def get_accessible_repositories(session: Session, user_id: int) -> list[Repository]:
    repositories = session.scalars(
        select(Repository)
        .join(RepositoryAccess, RepositoryAccess.repository_id == Repository.id)
        .where(RepositoryAccess.user_id == user_id)
        .order_by(Repository.full_name)
    ).all()
    return unique_repositories(repositories)


def require_repository_access(
    session: Session,
    current_user: AuthenticatedUser,
    repository_id: int,
) -> Repository:
    repository = session.scalar(
        select(Repository)
        .join(RepositoryAccess, RepositoryAccess.repository_id == Repository.id)
        .where(
            Repository.id == repository_id,
            RepositoryAccess.user_id == current_user.account.id,
        )
    )
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")
    return repository


def ensure_access(session: Session, user: UserAccount, repository: Repository) -> None:
    if repository.id is None:
        session.flush()
    access = session.scalar(
        select(RepositoryAccess).where(
            RepositoryAccess.user_id == user.id,
            RepositoryAccess.repository_id == repository.id,
        )
    )
    if access is None:
        session.add(RepositoryAccess(user_id=user.id, repository_id=repository.id, role="admin"))


def upsert_repository_from_github(
    session: Session,
    payload: dict[str, Any],
    installation: GitHubInstallation,
) -> Repository | None:
    if not payload.get("id"):
        return None

    github_repo_id = int(payload["id"])
    repository = session.scalar(select(Repository).where(Repository.github_repo_id == github_repo_id))
    full_name = payload.get("full_name") or ""
    if repository is None and full_name:
        repository = session.scalar(select(Repository).where(Repository.full_name == full_name))
    owner_login = ""
    if isinstance(payload.get("owner"), dict):
        owner_login = payload["owner"].get("login") or ""
    if not owner_login and payload.get("full_name"):
        owner_login = str(payload["full_name"]).split("/", 1)[0]

    if repository is None:
        repository = Repository(
            github_repo_id=github_repo_id,
            owner=owner_login,
            name=payload.get("name") or "",
            full_name=full_name,
        )
        session.add(repository)

    repository.installation = installation
    repository.github_repo_id = github_repo_id
    repository.owner = owner_login or repository.owner
    repository.name = payload.get("name") or repository.name
    repository.full_name = payload.get("full_name") or repository.full_name
    repository.default_branch = payload.get("default_branch") or repository.default_branch
    repository.private = bool(payload.get("private", repository.private))
    return repository


def sync_repositories_for_user(session: Session, account: UserAccount) -> list[str]:
    errors: list[str] = []
    installations = session.scalars(
        select(GitHubInstallation).where(GitHubInstallation.user_id == account.id)
    ).all()
    if not github_client.github_app_configured():
        return errors

    for installation in installations:
        try:
            token = github_client.installation_token(installation.github_installation_id).token
            for repo_payload in github_client.list_installation_repositories(token):
                repository = upsert_repository_from_github(session, repo_payload, installation)
                if repository is not None:
                    ensure_access(session, account, repository)
            session.commit()
        except httpx.HTTPStatusError as exc:
            errors.append(f"GitHub sync failed for {installation.account_login or installation.github_installation_id}: {exc.response.status_code}")
            session.rollback()
        except RuntimeError as exc:
            errors.append(str(exc))
            session.rollback()
    return errors


def installation_token_for_repository(repository: Repository) -> str:
    installation = repository.installation
    if installation is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository is not linked to a GitHub App installation.",
        )
    try:
        return github_client.installation_token(installation.github_installation_id).token
    except httpx.HTTPStatusError as exc:
        raise github_error(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def clean_constraints(constraints: list[str]) -> list[str]:
    cleaned: list[str] = []
    for constraint in constraints:
        value = " ".join(str(constraint).strip().split())
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def build_command_text(body: CommandCommentRequest) -> tuple[str, ParsedCommand]:
    if body.raw_command and body.raw_command.strip():
        command_text = body.raw_command.strip()
    else:
        command = body.command.strip().lower().lstrip("/")
        if command not in WORKBENCH_COMMANDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported AgentAway command.")
        suffix = " ".join(clean_constraints(body.constraints))
        command_text = f"/{command}{' ' + suffix if suffix else ''}"

    parsed = parse_agent_command(command_text)
    if parsed is None or parsed.command not in WORKBENCH_COMMANDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported AgentAway command.")
    if parsed.command in HIGH_RISK_COMMANDS and not body.confirm_implementation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Implementation commands require confirmation.",
        )
    return command_text, parsed


def latest_webhook_for_repositories(session: Session, repository_ids: list[int]) -> WebhookEvent | None:
    if not repository_ids:
        return None
    return session.scalar(
        select(WebhookEvent)
        .where(WebhookEvent.repository_id.in_(repository_ids))
        .order_by(desc(WebhookEvent.received_at))
        .limit(1)
    )


@router.get("/workbench")
def dashboard(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    sync_errors = sync_repositories_for_user(session, current_user.account)
    repositories = get_accessible_repositories(session, current_user.account.id)
    repository_ids = [repository.id for repository in repositories if repository.id is not None]
    installations = session.scalars(
        select(GitHubInstallation)
        .where(GitHubInstallation.user_id == current_user.account.id)
        .order_by(desc(GitHubInstallation.updated_at))
    ).unique().all()
    provider_count = session.scalar(
        select(ProviderCredential.id)
        .where(ProviderCredential.user_id == current_user.account.id)
        .limit(1)
    )
    latest_webhook = latest_webhook_for_repositories(session, repository_ids)

    runs_query = select(AgentRun).where(AgentRun.user_id == current_user.account.id)
    if repository_ids:
        runs_query = runs_query.where(AgentRun.repository_id.in_(repository_ids))
    recent_runs = session.scalars(runs_query.order_by(desc(AgentRun.updated_at)).limit(12)).all()

    setup_warnings: list[dict[str, str]] = []
    if provider_count is None:
        setup_warnings.append({"code": "missing_provider_key", "message": "Add a provider key before asking agents to plan or code."})
    if not installations:
        setup_warnings.append({"code": "missing_github_install", "message": "Install and link the GitHub App to load repositories."})
    if latest_webhook is None:
        setup_warnings.append({"code": "webhook_missing", "message": "No GitHub webhook deliveries have been seen for linked repositories."})
    elif latest_webhook.received_at < datetime.now(UTC) - timedelta(days=7):
        setup_warnings.append({"code": "webhook_stale", "message": "GitHub webhooks have not been seen in the last 7 days."})
    for message in sync_errors:
        setup_warnings.append({"code": "github_sync_failed", "message": message})

    return {
        "github_app_slug": settings.github_app_slug,
        "install_url": github_install_url(),
        "installations": [serialize_installation(installation) for installation in installations],
        "repositories": [serialize_repository(repository) for repository in repositories],
        "recent_runs": [serialize_run_card(run) for run in recent_runs],
        "setup_warnings": setup_warnings,
        "last_webhook_at": latest_webhook.received_at.isoformat() if latest_webhook else None,
    }


@router.get("/repositories")
def list_repositories(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    sync_errors = sync_repositories_for_user(session, current_user.account)
    repositories = get_accessible_repositories(session, current_user.account.id)
    return {
        "github_app_slug": settings.github_app_slug,
        "install_url": github_install_url(),
        "repositories": [serialize_repository(repository) for repository in repositories],
        "sync_errors": sync_errors,
    }


@router.get("/repositories/{repository_id}")
def get_repository(
    repository_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repository = require_repository_access(session, current_user, repository_id)
    recent_runs = session.scalars(
        select(AgentRun)
        .where(AgentRun.repository_id == repository.id, AgentRun.user_id == current_user.account.id)
        .order_by(desc(AgentRun.updated_at))
        .limit(8)
    ).all()
    events = session.scalars(
        select(WebhookEvent)
        .where(WebhookEvent.repository_id == repository.id)
        .order_by(desc(WebhookEvent.received_at))
        .limit(8)
    ).all()
    return {
        "repository": serialize_repository(repository),
        "recent_runs": [serialize_run_card(run) for run in recent_runs],
        "latest_activity": [
            {
                "id": event.id,
                "event": event.github_event,
                "action": event.action,
                "sender_login": event.sender_login,
                "received_at": event.received_at.isoformat(),
                "status": event.status,
            }
            for event in events
        ],
        "command_shortcuts": [
            {"label": "Plan", "command": "/plan add tests max 2 files"},
            {"label": "Fix Plan", "command": "/fixplan keep the change small"},
            {"label": "Proceed", "command": "/proceed"},
            {"label": "Fix", "command": "/fix add tests max 2 files"},
        ],
    }


@router.get("/repositories/{repository_id}/issues")
def list_issues(
    repository_id: int,
    state: str = Query(default="open", pattern="^(open|closed|all)$"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repository = require_repository_access(session, current_user, repository_id)
    token = installation_token_for_repository(repository)
    try:
        issues = github_client.list_issues(token, repository.full_name, state)
    except httpx.HTTPStatusError as exc:
        raise github_error(exc) from exc
    return {"issues": [serialize_issue(issue) for issue in issues]}


@router.post("/repositories/{repository_id}/issues", status_code=status.HTTP_201_CREATED)
def create_issue_for_repository(
    repository_id: int,
    body: IssueCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repository = require_repository_access(session, current_user, repository_id)
    token = installation_token_for_repository(repository)
    try:
        issue = github_client.create_issue(token, repository.full_name, body.title.strip(), body.body)
        command_comment = None
        run = None
        run_task_id = None
        if body.first_command != "none" or (body.raw_command and body.raw_command.strip()):
            constraints = body.constraints
            if not constraints and body.first_command in {"plan", "fix"} and not body.raw_command:
                constraints = ["add tests", "max 2 files"]
            command_text, parsed = build_command_text(
                CommandCommentRequest(
                    command=body.first_command,
                    constraints=constraints,
                    raw_command=body.raw_command,
                    confirm_implementation=body.confirm_implementation,
                )
            )
            command_comment = github_client.create_issue_comment(
                token,
                repository.full_name,
                int(issue["number"]),
                command_text,
            )
            run = create_authorized_command_run(
                session,
                current_user=current_user,
                repository=repository,
                issue=issue,
                comment=command_comment,
                parsed=parsed,
                trigger_type="web_workbench_command",
            )
            record_audit(
                session,
                user_id=current_user.account.id,
                action="workbench.command_posted",
                target_type="repository",
                target_id=str(repository.id),
                payload={"issue_number": issue.get("number"), "command": parsed.command, "agent_run_id": run.id},
            )
            session.commit()
            run_task_id = enqueue_agent_run(run)
            return {
                "issue": serialize_issue(issue),
                "command_comment": serialize_comment(command_comment),
                "command": parsed.to_dict(),
                "agent_run_id": run.id,
                "run_task_id": run_task_id,
            }
    except httpx.HTTPStatusError as exc:
        raise github_error(exc) from exc
    return {"issue": serialize_issue(issue), "command_comment": None, "command": None}


@router.get("/repositories/{repository_id}/issues/{issue_number}")
def get_issue_detail(
    repository_id: int,
    issue_number: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repository = require_repository_access(session, current_user, repository_id)
    token = installation_token_for_repository(repository)
    try:
        issue = github_client.get_issue(token, repository.full_name, issue_number)
    except httpx.HTTPStatusError as exc:
        raise github_error(exc) from exc
    related_runs = session.scalars(
        select(AgentRun)
        .where(
            AgentRun.repository_id == repository.id,
            AgentRun.issue_number == issue_number,
            AgentRun.user_id == current_user.account.id,
        )
        .order_by(desc(AgentRun.updated_at))
        .limit(8)
    ).all()
    return {
        "issue": serialize_issue(issue),
        "repository": serialize_repository(repository),
        "related_runs": [serialize_run_card(run) for run in related_runs],
    }


@router.get("/repositories/{repository_id}/issues/{issue_number}/comments")
def list_issue_comments(
    repository_id: int,
    issue_number: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repository = require_repository_access(session, current_user, repository_id)
    token = installation_token_for_repository(repository)
    try:
        comments = github_client.list_issue_comments(token, repository.full_name, issue_number)
    except httpx.HTTPStatusError as exc:
        raise github_error(exc) from exc
    return {"comments": [serialize_comment(comment) for comment in comments]}


@router.post("/repositories/{repository_id}/issues/{issue_number}/comments", status_code=status.HTTP_201_CREATED)
def create_issue_comment(
    repository_id: int,
    issue_number: int,
    body: CommentCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repository = require_repository_access(session, current_user, repository_id)
    token = installation_token_for_repository(repository)
    try:
        comment = github_client.create_issue_comment(token, repository.full_name, issue_number, body.body)
    except httpx.HTTPStatusError as exc:
        raise github_error(exc) from exc
    record_audit(
        session,
        user_id=current_user.account.id,
        action="workbench.issue_comment_created",
        target_type="repository",
        target_id=str(repository.id),
        payload={"issue_number": issue_number},
    )
    session.commit()
    return {"comment": serialize_comment(comment)}


@router.post("/repositories/{repository_id}/issues/{issue_number}/commands", status_code=status.HTTP_201_CREATED)
def create_command_comment(
    repository_id: int,
    issue_number: int,
    body: CommandCommentRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repository = require_repository_access(session, current_user, repository_id)
    command_text, parsed = build_command_text(body)
    if parsed.command in HIGH_RISK_COMMANDS:
        check_rate_limit(f"high-risk-command:{current_user.account.id}", limit=20)
    token = installation_token_for_repository(repository)
    try:
        issue = github_client.get_issue(token, repository.full_name, issue_number)
        comment = github_client.create_issue_comment(token, repository.full_name, issue_number, command_text)
    except httpx.HTTPStatusError as exc:
        raise github_error(exc) from exc
    run = create_authorized_command_run(
        session,
        current_user=current_user,
        repository=repository,
        issue=issue,
        comment=comment,
        parsed=parsed,
        trigger_type="web_workbench_command",
    )
    record_audit(
        session,
        user_id=current_user.account.id,
        action="workbench.command_posted",
        target_type="repository",
        target_id=str(repository.id),
        payload={"issue_number": issue_number, "command": parsed.command, "agent_run_id": run.id},
    )
    session.commit()
    run_task_id = enqueue_agent_run(run)
    return {
        "status": "comment_posted",
        "comment": serialize_comment(comment),
        "command": parsed.to_dict(),
        "agent_run_id": run.id,
        "run_task_id": run_task_id,
    }
