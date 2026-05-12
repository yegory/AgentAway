from __future__ import annotations

import re
from typing import Any

from services import github_app
from services.crypto import decrypt_secret
from services.db import add_run_event, load_provider_credential, update_run
from services.model_provider import chat_completion
from services.policy import permission_allowed


def command_modifiers(run: dict[str, Any]) -> dict[str, Any]:
    plan_json = run.get("plan_json") or {}
    command = plan_json.get("command") or {}
    modifiers = command.get("modifiers") or {}
    return modifiers if isinstance(modifiers, dict) else {}


def webhook_issue_context(run: dict[str, Any]) -> dict[str, str]:
    payload = run.get("webhook_payload") or {}
    issue = payload.get("issue") or {}
    comment = payload.get("comment") or {}
    return {
        "title": issue.get("title") or run.get("issue_title") or "",
        "body": issue.get("body") or "",
        "comment": comment.get("body") or "",
        "actor": run.get("trigger_actor") or "",
    }


def prepare_github_token(connection: Any, run: dict[str, Any]) -> str | None:
    installation_id = run.get("github_installation_id")
    if not installation_id:
        update_run(connection, run["id"], status="needs_github_app_installation")
        add_run_event(
            connection,
            run["id"],
            "github_app_missing",
            "Run is missing a GitHub App installation. Link the repository through the GitHub App flow.",
        )
        return None

    token = github_app.installation_token(int(installation_id)).token
    if run.get("trigger_type") in {"web_workbench_command", "api_v1_command"}:
        return token

    permission = github_app.collaborator_permission(token, run["full_name"], run["trigger_actor"])
    if not permission_allowed(permission):
        update_run(
            connection,
            run["id"],
            status="unauthorized_actor",
            error_message=f"{run['trigger_actor']} has repository permission '{permission}', which is not allowed.",
        )
        add_run_event(connection, run["id"], "unauthorized_actor", f"Actor permission was {permission}.")
        return None

    return token


def prepare_provider(connection: Any, run: dict[str, Any]) -> dict[str, str] | None:
    credential = load_provider_credential(connection, run.get("user_id"))
    if credential is None:
        update_run(connection, run["id"], status="needs_provider_key")
        add_run_event(connection, run["id"], "provider_key_missing", "No provider API key is configured.")
        return None

    provider = {
        "provider": credential["provider"],
        "api_key": decrypt_secret(credential["encrypted_api_key"]),
        "base_url": credential["base_url"],
        "model_name": credential["model_name"],
    }
    update_run(
        connection,
        run["id"],
        provider=provider["provider"],
        model_name=provider["model_name"],
    )
    return provider


def complete_with_provider(
    provider: dict[str, str],
    system_prompt: str,
    user_prompt: str,
) -> str:
    return chat_completion(
        provider=provider["provider"],
        api_key=provider["api_key"],
        base_url=provider["base_url"],
        model_name=provider["model_name"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


def safe_error_message(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(r"https://x-access-token:[^@]+@github\.com/", "https://x-access-token:<redacted>@github.com/", message)
    message = re.sub(r"\bgh[spuor]_[A-Za-z0-9_]+\b", "<redacted>", message)
    return message
