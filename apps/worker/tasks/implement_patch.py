from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from worker import celery_app

from services import github_app, settings
from services.db import add_run_event, engine, load_latest_plan, load_run, update_run
from services.model_provider import parse_json_object
from services.policy import validate_paths
from services.run_helpers import command_modifiers, complete_with_provider, prepare_github_token, prepare_provider, safe_error_message, webhook_issue_context
from workspace.docker_runner import run_command
from workspace.patcher import write_generated_files
from workspace.repo_cloner import clone_repository, git
from workspace.test_detector import detect_test_command


SYSTEM_PROMPT = """You are AgentAway's coding agent.
Generate a minimal safe file plan for the GitHub issue.
Return only JSON with keys: summary, files, commit_message.
files must be an array of objects with path and content.
Prefer small complete files. Do not edit secrets, workflows, keys, or environment files."""


def pr_body(run: dict[str, Any], generation: dict[str, Any], tests: dict[str, Any]) -> str:
    test_status = tests.get("status", "skipped")
    command = " ".join(tests.get("command") or [])
    return f"""AgentAway generated this draft PR from issue #{run['issue_number']}.

Summary:
{generation.get('summary') or 'No summary returned.'}

Tests:
- status: {test_status}
- command: `{command or 'not detected'}`

This PR is intentionally a draft. Review before merging.
"""


def run_tests(repo_path: Path) -> dict[str, Any]:
    command = detect_test_command(repo_path)
    if command is None:
        return {"status": "skipped", "command": None, "stdout": "", "stderr": ""}
    return run_command(command, repo_path, timeout_seconds=180)


def source_plan_block(plan: dict[str, Any] | None) -> str:
    if not plan:
        return "No prior plan was selected."
    return json.dumps(plan, indent=2, sort_keys=True)


@celery_app.task(name="pocket_maintainer.runs.implement_patch")
def implement_patch(agent_run_id: int) -> dict[str, object]:
    token = None
    provider = None
    run = None
    source_plan: dict[str, Any] | None = None
    source_plan_modifiers: dict[str, Any] = {}

    try:
        with engine.begin() as connection:
            run = load_run(connection, agent_run_id)
            if run is None:
                return {"status": "missing", "agent_run_id": agent_run_id}

            if run.get("command") == "proceed":
                latest_plan = load_latest_plan(connection, run)
                if latest_plan is None:
                    update_run(connection, agent_run_id, status="needs_plan")
                    add_run_event(
                        connection,
                        agent_run_id,
                        "plan_missing",
                        "No completed AgentAway plan exists for this issue yet.",
                    )
                    return {"status": "blocked", "agent_run_id": agent_run_id}

                latest_plan_json = latest_plan.get("plan_json") or {}
                source_plan = latest_plan_json.get("generated_plan")
                source_command = latest_plan_json.get("command") or {}
                source_plan_modifiers = source_command.get("modifiers") or {}
                run["plan_json"] = {
                    **(run.get("plan_json") or {}),
                    "source_plan_run_id": latest_plan["id"],
                    "source_plan_comment_url": latest_plan_json.get("github_comment_url"),
                    "source_generated_plan": source_plan,
                }
                update_run(connection, agent_run_id, plan_json=run["plan_json"])

            update_run(connection, agent_run_id, status="coding")
            add_run_event(connection, agent_run_id, "coding_started", "Fix task started.")
            token = prepare_github_token(connection, run)
            provider = prepare_provider(connection, run)

        if token is None or provider is None or run is None:
            return {"status": "blocked", "agent_run_id": agent_run_id}

        context = webhook_issue_context(run)
        modifiers = {**source_plan_modifiers, **command_modifiers(run)}
        max_files = int(modifiers.get("max_files") or 3)
        forbidden_paths = modifiers.get("forbidden_paths")
        prior_plan = source_plan_block(source_plan)
        user_prompt = f"""Repository: {run['full_name']}
Issue #{run['issue_number']}: {context['title']}

Issue body:
{context['body']}

Trigger comment:
{context['comment']}

Prior AgentAway plan to implement:
{prior_plan}

Constraints:
- Maximum files: {max_files}
- Forbidden paths: {forbidden_paths}
- Tests requested: {bool(modifiers.get('tests_required'))}
- If tests are requested, include a small test file when appropriate.
"""
        raw_generation = complete_with_provider(provider, SYSTEM_PROMPT, user_prompt)
        generation = parse_json_object(raw_generation)
        files = generation.get("files") or []
        if not isinstance(files, list) or not files:
            raise ValueError("Model did not return any files to write.")

        paths = [str(file_spec.get("path") or "") for file_spec in files]
        policy = validate_paths(paths, max_files=max_files, forbidden_paths=forbidden_paths)
        if not policy.allowed:
            raise ValueError(policy.reason)

        workspace = Path(settings.WORKSPACE_ROOT) / f"run-{agent_run_id}"
        repo_path = workspace / "repo"
        if workspace.exists():
            shutil.rmtree(workspace)
        branch_name = f"agentaway/issue-{run['issue_number']}-run-{agent_run_id}"

        clone_repository(github_app.authenticated_clone_url(token, run["full_name"]), repo_path, run["default_branch"])
        git(repo_path, "checkout", "-b", branch_name)
        git(repo_path, "config", "user.name", "AgentAway")
        git(repo_path, "config", "user.email", "agentaway@users.noreply.github.com")
        written_paths = write_generated_files(repo_path, files)
        tests = run_tests(repo_path)
        git(repo_path, "add", *written_paths)
        git(repo_path, "commit", "-m", generation.get("commit_message") or f"AgentAway fix for issue #{run['issue_number']}")
        head_sha = git(repo_path, "rev-parse", "HEAD").stdout.strip()
        git(repo_path, "push", "origin", branch_name, timeout_seconds=180)

        pr = github_app.create_draft_pr(
            token=token,
            full_name=run["full_name"],
            title=f"AgentAway fix for issue #{run['issue_number']}",
            body=pr_body(run, generation, tests),
            head=branch_name,
            base=run["default_branch"],
        )
        github_app.issue_comment(
            token,
            run["full_name"],
            int(run["issue_number"]),
            f"AgentAway opened draft PR #{pr.get('number')}: {pr.get('html_url')}",
        )

        with engine.begin() as connection:
            update_run(
                connection,
                agent_run_id,
                status="draft_pr_opened",
                branch_name=branch_name,
                head_sha=head_sha,
                pull_request_number=pr.get("number"),
                pull_request_url=pr.get("html_url") or "",
                diff_summary_json={"files": written_paths, "summary": generation.get("summary")},
                test_summary_json=tests,
            )
            add_run_event(connection, agent_run_id, "draft_pr_opened", "Draft PR was opened.", {"url": pr.get("html_url")})

        return {"status": "draft_pr_opened", "agent_run_id": agent_run_id, "pull_request_url": pr.get("html_url")}
    except Exception as exc:
        message = safe_error_message(exc)
        with engine.begin() as connection:
            update_run(connection, agent_run_id, status="failed", error_message=message)
            add_run_event(connection, agent_run_id, "failed", message)
        return {"status": "failed", "agent_run_id": agent_run_id, "error": message}
