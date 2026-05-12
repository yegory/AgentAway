from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from app.config import settings


GITHUB_API = "https://api.github.com"


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: str


def github_app_configured() -> bool:
    return bool(settings.github_app_id and settings.github_app_private_key_base64)


def private_key_pem() -> str:
    if not settings.github_app_private_key_base64:
        raise RuntimeError("GITHUB_APP_PRIVATE_KEY_BASE64 is not configured.")
    return base64.b64decode(settings.github_app_private_key_base64).decode("utf-8")


def app_jwt() -> str:
    if not settings.github_app_id:
        raise RuntimeError("GITHUB_APP_ID is not configured.")
    now = int(time.time())
    return jwt.encode(
        {
            "iat": now - 60,
            "exp": now + 540,
            "iss": settings.github_app_id,
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


def split_repo(full_name: str) -> tuple[str, str]:
    owner, repo = full_name.split("/", 1)
    return owner, repo


def installation_token(installation_id: int) -> InstallationToken:
    response = httpx.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers=github_headers(app_jwt()),
        timeout=20,
    )
    response.raise_for_status()
    body = response.json()
    return InstallationToken(token=body["token"], expires_at=body["expires_at"])


def paginated_get(token: str, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        request_params = {"per_page": 100, "page": page, **(params or {})}
        response = httpx.get(
            f"{GITHUB_API}{path}",
            headers=github_headers(token),
            params=request_params,
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()
        page_items = body.get("repositories") if isinstance(body, dict) else body
        if not isinstance(page_items, list):
            return items
        items.extend(item for item in page_items if isinstance(item, dict))
        if len(page_items) < request_params["per_page"]:
            return items
        page += 1


def list_installation_repositories(token: str) -> list[dict[str, Any]]:
    return paginated_get(token, "/installation/repositories")


def list_issues(token: str, full_name: str, state: str = "open") -> list[dict[str, Any]]:
    owner, repo = split_repo(full_name)
    issues = paginated_get(
        token,
        f"/repos/{owner}/{repo}/issues",
        {"state": state, "sort": "updated", "direction": "desc"},
    )
    return [issue for issue in issues if "pull_request" not in issue]


def get_issue(token: str, full_name: str, issue_number: int) -> dict[str, Any]:
    owner, repo = split_repo(full_name)
    response = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}",
        headers=github_headers(token),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def list_issue_comments(token: str, full_name: str, issue_number: int) -> list[dict[str, Any]]:
    owner, repo = split_repo(full_name)
    return paginated_get(
        token,
        f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
        {"sort": "created", "direction": "asc"},
    )


def create_issue(token: str, full_name: str, title: str, body: str) -> dict[str, Any]:
    owner, repo = split_repo(full_name)
    response = httpx.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues",
        headers=github_headers(token),
        json={"title": title, "body": body},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def create_issue_comment(token: str, full_name: str, issue_number: int, body: str) -> dict[str, Any]:
    owner, repo = split_repo(full_name)
    response = httpx.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}/comments",
        headers=github_headers(token),
        json={"body": body},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()
