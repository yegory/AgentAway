from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.db import get_session
from app.models import AgentRun, GitHubInstallation, Repository, RepositoryAccess, UserAccount, WebhookEvent
from app.services.auth import upsert_user_account
from app.services.command_parser import ParsedCommand, parse_agent_command


router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def verify_github_signature(raw_body: bytes, signature_header: str | None, secret: str) -> None:
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GITHUB_WEBHOOK_SECRET is not configured.",
        )

    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing GitHub signature.")

    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GitHub signature.")


def upsert_installation(session: Session, payload: dict[str, Any]) -> GitHubInstallation | None:
    installation = payload.get("installation")
    if not isinstance(installation, dict) or not installation.get("id"):
        return None

    github_installation_id = int(installation["id"])
    db_installation = session.scalar(
        select(GitHubInstallation).where(
            GitHubInstallation.github_installation_id == github_installation_id
        )
    )

    account = installation.get("account") or {}
    if db_installation is None:
        db_installation = GitHubInstallation(github_installation_id=github_installation_id)
        session.add(db_installation)

    db_installation.account_login = account.get("login") or db_installation.account_login or ""
    db_installation.account_type = account.get("type") or db_installation.account_type or ""
    db_installation.permissions_json = installation.get("permissions") or {}
    return db_installation


def upsert_repository(
    session: Session,
    payload: dict[str, Any],
    installation: GitHubInstallation | None,
) -> Repository | None:
    repository = payload.get("repository")
    if not isinstance(repository, dict) or not repository.get("id"):
        return None

    github_repo_id = int(repository["id"])
    db_repository = session.scalar(
        select(Repository).where(Repository.github_repo_id == github_repo_id)
    )
    full_name = repository.get("full_name") or ""
    if db_repository is None and full_name:
        db_repository = session.scalar(select(Repository).where(Repository.full_name == full_name))

    owner = repository.get("owner") or {}
    if db_repository is None:
        db_repository = Repository(
            github_repo_id=github_repo_id,
            owner=owner.get("login") or "",
            name=repository.get("name") or "",
            full_name=full_name,
        )
        session.add(db_repository)

    db_repository.installation = installation
    db_repository.github_repo_id = github_repo_id
    db_repository.owner = owner.get("login") or db_repository.owner
    db_repository.name = repository.get("name") or db_repository.name
    db_repository.full_name = full_name or db_repository.full_name
    db_repository.default_branch = repository.get("default_branch") or db_repository.default_branch
    db_repository.private = bool(repository.get("private", db_repository.private))
    return db_repository


def upsert_repository_from_summary(
    session: Session,
    repository: dict[str, Any],
    installation: GitHubInstallation | None,
) -> Repository | None:
    if not repository.get("id"):
        return None

    github_repo_id = int(repository["id"])
    db_repository = session.scalar(
        select(Repository).where(Repository.github_repo_id == github_repo_id)
    )
    full_name = repository.get("full_name") or ""
    if db_repository is None and full_name:
        db_repository = session.scalar(select(Repository).where(Repository.full_name == full_name))

    owner_login = ""
    if isinstance(repository.get("owner"), dict):
        owner_login = repository["owner"].get("login") or ""
    if not owner_login and full_name:
        owner_login = str(full_name).split("/", 1)[0]

    if db_repository is None:
        db_repository = Repository(
            github_repo_id=github_repo_id,
            owner=owner_login,
            name=repository.get("name") or "",
            full_name=full_name,
        )
        session.add(db_repository)

    db_repository.installation = installation
    db_repository.github_repo_id = github_repo_id
    db_repository.owner = owner_login or db_repository.owner
    db_repository.name = repository.get("name") or db_repository.name
    db_repository.full_name = full_name or db_repository.full_name
    db_repository.default_branch = repository.get("default_branch") or db_repository.default_branch
    db_repository.private = bool(repository.get("private", db_repository.private))
    return db_repository


def ensure_repository_access(
    session: Session,
    user: UserAccount | None,
    repository: Repository | None,
) -> None:
    if user is None or repository is None:
        return

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


def command_from_payload(github_event: str, payload: dict[str, Any]) -> ParsedCommand | None:
    if github_event != "issue_comment":
        return None

    if payload.get("action") != "created":
        return None

    comment = payload.get("comment")
    if not isinstance(comment, dict):
        return None

    return parse_agent_command(comment.get("body"))


def create_agent_run_for_command(
    session: Session,
    delivery_id: str,
    user: UserAccount | None,
    repository: Repository | None,
    payload: dict[str, Any],
    parsed_command: ParsedCommand,
) -> AgentRun | None:
    if parsed_command.command not in {"plan", "fixplan", "fix", "proceed"}:
        return None

    issue = payload.get("issue") or {}
    comment = payload.get("comment") or {}
    sender = payload.get("sender") or {}
    actor = (comment.get("user") or {}).get("login") or sender.get("login") or ""

    run = AgentRun(
        user=user,
        repository=repository,
        issue_number=issue.get("number"),
        issue_title=issue.get("title") or "",
        issue_url=issue.get("html_url") or "",
        comment_url=comment.get("html_url") or "",
        github_delivery_id=delivery_id,
        trigger_type="github_issue_comment",
        trigger_actor=actor,
        command=parsed_command.command,
        status=f"queued_{parsed_command.command}",
        plan_json={
            "command": parsed_command.to_dict(),
            "author_association": comment.get("author_association") or "",
        },
    )
    session.add(run)
    return run


def user_for_installation(session: Session, installation: GitHubInstallation | None) -> UserAccount | None:
    if installation and installation.user_id:
        return session.get(UserAccount, installation.user_id)
    if settings.app_env == "development":
        return upsert_user_account(
            session,
            clerk_user_id=settings.agentaway_dev_user_id,
            email="dev@agentaway.local",
            display_name="Local Dev",
        )
    return None


def sync_installation_repositories(
    session: Session,
    payload: dict[str, Any],
    installation: GitHubInstallation | None,
) -> None:
    user = user_for_installation(session, installation)
    repositories: list[dict[str, Any]] = []

    if isinstance(payload.get("repositories"), list):
        repositories.extend(payload["repositories"])
    if isinstance(payload.get("repositories_added"), list):
        repositories.extend(payload["repositories_added"])

    for repository_payload in repositories:
        if isinstance(repository_payload, dict):
            repository = upsert_repository_from_summary(session, repository_payload, installation)
            ensure_repository_access(session, user, repository)


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(alias="X-GitHub-Event"),
    x_github_delivery: str = Header(alias="X-GitHub-Delivery"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    raw_body = await request.body()
    verify_github_signature(raw_body, x_hub_signature_256, settings.github_webhook_secret)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.") from exc

    existing_event = session.scalar(
        select(WebhookEvent).where(WebhookEvent.github_delivery_id == x_github_delivery)
    )
    if existing_event is not None:
        return {
            "status": "duplicate",
            "event_id": existing_event.id,
            "github_delivery_id": x_github_delivery,
        }

    installation = upsert_installation(session, payload)
    repository = upsert_repository(session, payload, installation)
    user = user_for_installation(session, installation)
    ensure_repository_access(session, user, repository)
    sync_installation_repositories(session, payload, installation)

    action = str(payload.get("action") or "")
    parsed_command = command_from_payload(x_github_event, payload)
    sender = payload.get("sender") or {}

    webhook_event = WebhookEvent(
        github_delivery_id=x_github_delivery,
        github_event=x_github_event,
        action=action,
        installation=installation,
        repository=repository,
        sender_login=sender.get("login") or "",
        payload_json=payload,
        status="queued",
    )
    session.add(webhook_event)

    run = None
    if parsed_command is not None:
        run = create_agent_run_for_command(
            session=session,
            delivery_id=x_github_delivery,
            user=user,
            repository=repository,
            payload=payload,
            parsed_command=parsed_command,
        )

    session.commit()

    webhook_task = celery_app.send_task(
        "pocket_maintainer.webhooks.handle",
        kwargs={"webhook_event_id": webhook_event.id, "agent_run_id": run.id if run else None},
    )
    run_task_id = None
    if run is not None and parsed_command is not None:
        task_name = {
            "plan": "pocket_maintainer.runs.create_plan",
            "fixplan": "pocket_maintainer.runs.create_plan",
            "fix": "pocket_maintainer.runs.implement_patch",
            "proceed": "pocket_maintainer.runs.implement_patch",
        }.get(parsed_command.command)
        if task_name:
            run_task = celery_app.send_task(task_name, kwargs={"agent_run_id": run.id})
            run_task_id = run_task.id

    return {
        "status": "accepted",
        "event_id": webhook_event.id,
        "agent_run_id": run.id if run else None,
        "task_id": webhook_task.id,
        "run_task_id": run_task_id,
        "command": parsed_command.to_dict() if parsed_command else None,
    }
