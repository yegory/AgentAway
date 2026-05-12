from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from services import settings


GITHUB_API = "https://api.github.com"


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: str


def private_key_pem() -> str:
    if not settings.GITHUB_APP_PRIVATE_KEY_BASE64:
        raise RuntimeError("GITHUB_APP_PRIVATE_KEY_BASE64 is not configured.")
    return base64.b64decode(settings.GITHUB_APP_PRIVATE_KEY_BASE64).decode("utf-8")


def app_jwt() -> str:
    if not settings.GITHUB_APP_ID:
        raise RuntimeError("GITHUB_APP_ID is not configured.")
    now = int(time.time())
    return jwt.encode(
        {
            "iat": now - 60,
            "exp": now + 540,
            "iss": settings.GITHUB_APP_ID,
        },
        private_key_pem(),
        algorithm="RS256",
    )


def github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def installation_token(installation_id: int) -> InstallationToken:
    response = httpx.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers=github_headers(app_jwt()),
        timeout=20,
    )
    response.raise_for_status()
    body = response.json()
    return InstallationToken(token=body["token"], expires_at=body["expires_at"])


def split_repo(full_name: str) -> tuple[str, str]:
    owner, repo = full_name.split("/", 1)
    return owner, repo


def issue_comment(token: str, full_name: str, issue_number: int, body: str) -> dict[str, Any]:
    owner, repo = split_repo(full_name)
    response = httpx.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}/comments",
        headers=github_headers(token),
        json={"body": body},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def collaborator_permission(token: str, full_name: str, username: str) -> str:
    owner, repo = split_repo(full_name)
    response = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/collaborators/{username}/permission",
        headers=github_headers(token),
        timeout=20,
    )
    if response.status_code == 404:
        return "none"
    response.raise_for_status()
    return response.json().get("permission") or "none"


def get_issue(token: str, full_name: str, issue_number: int) -> dict[str, Any]:
    owner, repo = split_repo(full_name)
    response = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}",
        headers=github_headers(token),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def create_draft_pr(
    token: str,
    full_name: str,
    title: str,
    body: str,
    head: str,
    base: str,
) -> dict[str, Any]:
    owner, repo = split_repo(full_name)
    response = httpx.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        headers=github_headers(token),
        json={"title": title, "body": body, "head": head, "base": base, "draft": True},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def authenticated_clone_url(token: str, full_name: str) -> str:
    return f"https://x-access-token:{token}@github.com/{full_name}.git"
