from __future__ import annotations

from typing import Any

from worker import celery_app

from services import github_app
from services.db import add_run_event, engine, load_latest_plan, load_run, update_run
from services.model_provider import parse_json_object
from services.run_helpers import complete_with_provider, prepare_github_token, prepare_provider, safe_error_message, webhook_issue_context


SYSTEM_PROMPT = """You are AgentAway's planning agent.
Create a concise, implementation-ready plan for the GitHub issue.
Return only JSON with keys: summary, steps, files, tests, risks.
steps, files, tests, and risks must be arrays of short strings."""


def plan_comment(run: dict[str, Any], plan: dict[str, Any]) -> str:
    noun = "revised plan" if run.get("command") == "fixplan" else "plan"
    steps = "\n".join(f"- {step}" for step in plan.get("steps", [])) or "- No steps returned."
    files = "\n".join(f"- `{path}`" for path in plan.get("files", [])) or "- Files not identified yet."
    tests = "\n".join(f"- {test}" for test in plan.get("tests", [])) or "- No tests identified yet."
    risks = "\n".join(f"- {risk}" for risk in plan.get("risks", [])) or "- No notable risks."
    return f"""### AgentAway {noun} for issue #{run['issue_number']}

{plan.get('summary') or 'Plan generated.'}

**Steps**
{steps}

**Likely files**
{files}

**Tests**
{tests}

**Risks**
{risks}
"""


@celery_app.task(name="pocket_maintainer.runs.create_plan")
def create_plan(agent_run_id: int) -> dict[str, object]:
    token = None
    provider = None
    run = None
    source_plan: dict[str, Any] | None = None

    try:
        with engine.begin() as connection:
            run = load_run(connection, agent_run_id)
            if run is None:
                return {"status": "missing", "agent_run_id": agent_run_id}

            if run.get("command") == "fixplan":
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
                run["plan_json"] = {
                    **(run.get("plan_json") or {}),
                    "source_plan_run_id": latest_plan["id"],
                    "source_plan_comment_url": latest_plan_json.get("github_comment_url"),
                    "source_generated_plan": source_plan,
                }
                update_run(connection, agent_run_id, plan_json=run["plan_json"])

            update_run(connection, agent_run_id, status="planning")
            add_run_event(connection, agent_run_id, "planning_started", "Planning task started.")
            token = prepare_github_token(connection, run)
            provider = prepare_provider(connection, run)

        if token is None or provider is None or run is None:
            return {"status": "blocked", "agent_run_id": agent_run_id}

        context = webhook_issue_context(run)
        user_prompt = f"""Repository: {run['full_name']}
Issue #{run['issue_number']}: {context['title']}

Issue body:
{context['body']}

Trigger comment:
{context['comment']}

Previous AgentAway plan:
{source_plan or 'No previous plan selected.'}

If there is a previous plan, evaluate it against the trigger comment and return a revised plan.
"""
        raw_plan = complete_with_provider(provider, SYSTEM_PROMPT, user_prompt)
        plan = parse_json_object(raw_plan)
        comment = github_app.issue_comment(token, run["full_name"], int(run["issue_number"]), plan_comment(run, plan))

        with engine.begin() as connection:
            update_run(
                connection,
                agent_run_id,
                status="planned",
                plan_json={
                    **(run.get("plan_json") or {}),
                    "generated_plan": plan,
                    "github_comment_url": comment.get("html_url"),
                },
            )
            add_run_event(connection, agent_run_id, "plan_commented", "Plan was posted back to GitHub.")

        return {"status": "planned", "agent_run_id": agent_run_id}
    except Exception as exc:
        message = safe_error_message(exc)
        with engine.begin() as connection:
            update_run(connection, agent_run_id, status="failed", error_message=message)
            add_run_event(connection, agent_run_id, "failed", message)
        return {"status": "failed", "agent_run_id": agent_run_id, "error": message}
