from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.config import settings
from app.models import GitHubInstallation, Repository, RepositoryAccess
from app.services.audit_log import record_audit
from app.services.auth import AuthenticatedUser, get_current_user


router = APIRouter(prefix="/api/github", tags=["github"])
installations_router = APIRouter(prefix="/api/installations", tags=["github"])


class InstallationLinkRequest(BaseModel):
    installation_id: int


def serialize_repository(repository: Repository) -> dict[str, object]:
    return {
        "id": repository.id,
        "github_repo_id": repository.github_repo_id,
        "owner": repository.owner,
        "name": repository.name,
        "full_name": repository.full_name,
        "default_branch": repository.default_branch,
        "private": repository.private,
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


@installations_router.get("")
def list_installations(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    installations = session.scalars(
        select(GitHubInstallation)
        .where(GitHubInstallation.user_id == current_user.account.id)
        .order_by(desc(GitHubInstallation.updated_at))
    ).unique().all()
    return {
        "github_app_slug": settings.github_app_slug,
        "install_url": github_install_url(),
        "installations": [serialize_installation(installation) for installation in installations],
    }


@router.post("/installations/link")
def link_installation(
    body: InstallationLinkRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    installation = session.scalar(
        select(GitHubInstallation).where(
            GitHubInstallation.github_installation_id == body.installation_id
        )
    )
    if installation is None:
        installation = GitHubInstallation(github_installation_id=body.installation_id)
        session.add(installation)

    if installation.user_id and installation.user_id != current_user.account.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This GitHub installation is already linked to another account.",
        )

    installation.user_id = current_user.account.id
    for repository in installation.repositories:
        access = session.scalar(
            select(RepositoryAccess).where(
                RepositoryAccess.user_id == current_user.account.id,
                RepositoryAccess.repository_id == repository.id,
            )
        )
        if access is None:
            session.add(
                RepositoryAccess(
                    user_id=current_user.account.id,
                    repository_id=repository.id,
                    role="admin",
                )
            )

    record_audit(
        session,
        user_id=current_user.account.id,
        action="github_installation.linked",
        target_type="github_installation",
        target_id=str(installation.github_installation_id),
        payload={"account_login": installation.account_login},
    )
    session.commit()
    session.refresh(installation)
    return {"installation": serialize_installation(installation)}
