"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CommandComposer } from "./CommandComposer";
import { AgentCommand } from "../lib/commands";
import { useApiSession } from "../lib/useApiSession";

type RunDetail = {
  id: number;
  repository_id: number | null;
  repository: { id: number; full_name: string; default_branch: string } | null;
  issue_number: number | null;
  issue_title: string;
  issue_url: string;
  comment_url: string;
  command: string;
  status: string;
  provider: string | null;
  model_name: string | null;
  branch_name: string | null;
  pull_request_url: string;
  pull_request_number: number | null;
  plan_json: Record<string, unknown> | null;
  diff_summary_json: Record<string, unknown> | null;
  test_summary_json: Record<string, unknown> | null;
  error_message: string | null;
  cancellation_requested: boolean;
  events: Array<{
    id: number;
    event_type: string;
    message: string;
    payload_json: Record<string, unknown>;
    created_at: string;
  }>;
};

type State =
  | { state: "loading" }
  | { state: "ok"; run: RunDetail }
  | { state: "error"; message: string };

export function RunDetailClient({ runId }: { runId: string }) {
  const session = useApiSession();
  const [data, setData] = useState<State>({ state: "loading" });
  const [composerCommand, setComposerCommand] = useState<AgentCommand | null>(null);
  const [actionMessage, setActionMessage] = useState("");

  async function load() {
    if (!session.ready || !session.signedIn) {
      return;
    }
    try {
      const response = await session.fetchApi(`/api/runs/${runId}`);
      const body = await response.json();
      setData(response.ok ? { state: "ok", run: body } : { state: "error", message: "Run not found." });
    } catch {
      setData({ state: "error", message: "API is unreachable." });
    }
  }

  useEffect(() => {
    load();
  }, [session.ready, session.signedIn, runId]);

  async function stopRun() {
    setActionMessage("Requesting stop.");
    try {
      const response = await session.fetchApi(`/api/runs/${runId}/stop`, { method: "POST" });
      setActionMessage(response.ok ? "Stop requested." : "Run is not stoppable.");
      await load();
    } catch {
      setActionMessage("API is unreachable.");
    }
  }

  if (!session.ready || data.state === "loading") {
    return <RunDetailLoading />;
  }
  if (!session.signedIn) {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Sign in</span>
        <h2>Sign in to view this run.</h2>
      </section>
    );
  }
  if (data.state === "error") {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Unavailable</span>
        <h2>{data.message}</h2>
      </section>
    );
  }

  const run = data.run;
  const issueNumber = run.issue_number;
  const repositoryId = run.repository?.id ?? run.repository_id;
  const commandContext =
    typeof repositoryId === "number" && typeof issueNumber === "number"
      ? { repositoryId, issueNumber }
      : null;
  const retryCommand = toWorkbenchCommand(run.command);
  const runState = runStateCopy(run);

  return (
    <div className="stack">
      <section className="panel stack run-hero">
        <div className="status-row">
          <div>
            <span className="eyebrow">Run #{run.id}</span>
            <h2>{runState.title}</h2>
            <p className="muted">{runState.description}</p>
          </div>
          <span className={`pill status-${run.status}`}>{formatStatus(run.status)}</span>
        </div>
        <div className="run-subject">
          <strong>{run.issue_title || `Issue #${run.issue_number ?? "unknown"}`}</strong>
          <span>{run.repository?.full_name ?? "unknown repo"} - /{run.command}</span>
        </div>
        <div className="detail-grid">
          <Metric label="Issue" value={run.issue_number ? `#${run.issue_number}` : "unknown"} />
          <Metric label="Branch" value={run.branch_name ?? "pending"} />
          <Metric label="Provider" value={run.provider ? `${run.provider} ${run.model_name ?? ""}` : "pending"} />
        </div>
        <div className="action-strip">
          {run.pull_request_url ? (
            <a className="primary-action" href={run.pull_request_url}>
              Open draft PR
            </a>
          ) : null}
          {commandContext ? (
            <Link className="nav-link" href={`/repos/${commandContext.repositoryId}/issues/${commandContext.issueNumber}`}>
              Open issue
            </Link>
          ) : null}
          {run.comment_url ? <a className="nav-link" href={run.comment_url}>Trigger comment</a> : null}
          {run.issue_url ? <a className="nav-link" href={run.issue_url}>GitHub issue</a> : null}
        </div>
      </section>

      <PlanPanel planJson={run.plan_json} />
      <DiffPanel value={run.diff_summary_json} />
      <TestsPanel value={run.test_summary_json} />

      {run.pull_request_url ? (
        <section className="panel stack">
          <div className="status-row">
            <h2>Draft PR</h2>
            <span className="pill">draft only</span>
          </div>
          <a className="primary-action" href={run.pull_request_url}>
            Open PR #{run.pull_request_number ?? ""}
          </a>
        </section>
      ) : null}

      {run.error_message ? (
        <section className="panel empty-state">
          <span className="pill warn">Error</span>
          <pre className="text-body">{run.error_message}</pre>
        </section>
      ) : null}

      <section className="panel stack">
        <h2>Next actions</h2>
        {commandContext ? (
          <>
            <div className="next-action-grid">
              <ActionButton
                description="Ask AgentAway for a smaller or more constrained plan."
                label="Revise plan"
                onClick={() => setComposerCommand("fixplan")}
              />
              <ActionButton
                description="Start implementation from the latest plan. Requires confirmation."
                label="Proceed"
                onClick={() => setComposerCommand("proceed")}
              />
              {retryCommand ? (
                <ActionButton
                  description={`Post another /${retryCommand} command on the issue.`}
                  label="Retry"
                  onClick={() => setComposerCommand(retryCommand)}
                />
              ) : null}
              {isStoppable(run) ? (
                <ActionButton
                  description="Request cancellation. The worker stops only at supported checkpoints."
                  label="Stop"
                  onClick={stopRun}
                />
              ) : null}
            </div>
            {composerCommand ? (
              <CommandComposer
                initialCommand={composerCommand}
                issueNumber={commandContext.issueNumber}
                onPosted={load}
                repositoryId={commandContext.repositoryId}
              />
            ) : null}
          </>
        ) : (
          <p className="muted">This run is missing repository or issue context, so command actions are unavailable.</p>
        )}
        {actionMessage ? <p className="muted">{actionMessage}</p> : null}
      </section>

      <section className="panel stack">
        <h2>Timeline</h2>
        {run.events.length === 0 ? (
          <p className="muted">No worker events recorded yet.</p>
        ) : (
          <div className="timeline">
            {run.events.map((event) => (
              <article className="timeline-item" key={event.id}>
                <span>{new Date(event.created_at).toLocaleString()}</span>
                <strong>{event.event_type.replaceAll("_", " ")}</strong>
                <p>{event.message}</p>
                {Object.keys(event.payload_json || {}).length ? (
                  <RawDetails title="Event details" value={event.payload_json} />
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function RunDetailLoading() {
  return (
    <section className="panel empty-state">
      <span className="pill warn">Loading</span>
      <h2>Loading run detail.</h2>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ActionButton({
  label,
  description,
  onClick,
}: {
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button className="action-card" onClick={onClick} type="button">
      <strong>{label}</strong>
      <span>{description}</span>
    </button>
  );
}

function PlanPanel({ planJson }: { planJson: Record<string, unknown> | null }) {
  if (!planJson) {
    return null;
  }
  const generatedPlan = extractPlan(planJson);
  const sourcePlan = objectValue(planJson.source_generated_plan);
  const commentUrl = typeof planJson.github_comment_url === "string" ? planJson.github_comment_url : "";
  const sourceCommentUrl =
    typeof planJson.source_plan_comment_url === "string" ? planJson.source_plan_comment_url : "";

  return (
    <section className="panel stack">
      <div className="status-row">
        <h2>Plan</h2>
        {commentUrl ? <a className="nav-link" href={commentUrl}>GitHub comment</a> : null}
      </div>
      {generatedPlan ? (
        <ReadablePlan plan={generatedPlan} />
      ) : sourcePlan ? null : (
        <RawDetails title="Plan data" value={planJson} />
      )}
      {sourcePlan ? (
        <div className="source-plan">
          <div className="status-row">
            <h3>Source plan</h3>
            {sourceCommentUrl ? <a className="subtle-link" href={sourceCommentUrl}>Original comment</a> : null}
          </div>
          <ReadablePlan plan={sourcePlan} />
        </div>
      ) : null}
      {!generatedPlan && sourcePlan ? <RawDetails title="Run plan metadata" value={planJson} /> : null}
    </section>
  );
}

function ReadablePlan({ plan }: { plan: Record<string, unknown> }) {
  return (
    <div className="readable-plan">
      {typeof plan.summary === "string" ? <p className="summary-card">{plan.summary}</p> : null}
      <PlanList title="Steps" value={plan.steps} />
      <PlanList title="Files" value={plan.files} variant="file" />
      <PlanList title="Tests" value={plan.tests} />
      <PlanList title="Risks" value={plan.risks} variant="risk" />
    </div>
  );
}

function PlanList({
  title,
  value,
  variant = "plain",
}: {
  title: string;
  value: unknown;
  variant?: "plain" | "file" | "risk";
}) {
  const items = Array.isArray(value) ? value : [];
  if (!items.length) {
    return null;
  }
  return (
    <div className={`plan-list plan-list-${variant}`}>
      <strong>{title}</strong>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>
            {variant === "file" ? <code>{String(item)}</code> : String(item)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DiffPanel({ value }: { value: unknown }) {
  if (!value) {
    return null;
  }
  const summary = objectValue(value);
  const files = Array.isArray(summary?.files) ? summary.files.map(String) : [];
  const text = typeof summary?.summary === "string" ? summary.summary : "";

  return (
    <section className="panel stack">
      <h2>Changes</h2>
      {text ? <p className="summary-card">{text}</p> : null}
      {files.length ? (
        <div className="file-list">
          {files.map((file) => (
            <code key={file}>{file}</code>
          ))}
        </div>
      ) : (
        <p className="muted">No file summary recorded yet.</p>
      )}
      <RawDetails title="Raw change data" value={value} />
    </section>
  );
}

function TestsPanel({ value }: { value: unknown }) {
  if (!value) {
    return null;
  }
  const summary = objectValue(value);
  const status = typeof summary?.status === "string" ? summary.status : "recorded";
  const command = Array.isArray(summary?.command)
    ? summary.command.map(String).join(" ")
    : typeof summary?.command === "string"
      ? summary.command
      : "";
  const stdout = typeof summary?.stdout === "string" ? summary.stdout.trim() : "";
  const stderr = typeof summary?.stderr === "string" ? summary.stderr.trim() : "";

  return (
    <section className="panel stack">
      <div className="status-row">
        <h2>Tests</h2>
        <span className={`pill ${status === "failed" ? "warn" : ""}`}>{status}</span>
      </div>
      {command ? (
        <div className="summary-card">
          <span className="eyebrow">Command</span>
          <code>{command}</code>
        </div>
      ) : (
        <p className="muted">No test command was detected or recorded.</p>
      )}
      {stdout || stderr ? (
        <details className="details-panel">
          <summary>Output</summary>
          {stdout ? <pre className="text-body">{stdout}</pre> : null}
          {stderr ? <pre className="text-body">{stderr}</pre> : null}
        </details>
      ) : null}
      <RawDetails title="Raw test data" value={value} />
    </section>
  );
}

function RawDetails({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="details-panel">
      <summary>{title}</summary>
      <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function extractPlan(planJson: Record<string, unknown>) {
  const generated = objectValue(planJson.generated_plan);
  if (generated) {
    return generated;
  }
  if (
    typeof planJson.summary === "string" ||
    Array.isArray(planJson.steps) ||
    Array.isArray(planJson.files) ||
    Array.isArray(planJson.tests) ||
    Array.isArray(planJson.risks)
  ) {
    return planJson;
  }
  return null;
}

function toWorkbenchCommand(command: string): AgentCommand | null {
  if (command === "plan" || command === "fixplan" || command === "proceed" || command === "fix") {
    return command;
  }
  return null;
}

function runStateCopy(run: RunDetail) {
  const issue = run.issue_number ? `issue #${run.issue_number}` : "this issue";
  switch (run.status) {
    case "draft_pr_opened":
      return {
        title: "Draft PR ready",
        description: `AgentAway opened a draft pull request for ${issue}. Review it in GitHub before merging.`,
      };
    case "planned":
      return {
        title: "Plan ready",
        description: `A plan is ready for ${issue}. Revise it or proceed when you are comfortable.`,
      };
    case "coding":
      return {
        title: "Implementation running",
        description: `AgentAway is working on ${issue}. Watch the timeline for worker updates.`,
      };
    case "failed":
      return {
        title: "Run failed",
        description: `The worker stopped before finishing ${issue}. Check the redacted error and retry with tighter constraints.`,
      };
    case "needs_plan":
      return {
        title: "Needs a plan",
        description: "Proceed needs a completed plan first. Ask for a plan or revise an earlier one.",
      };
    case "needs_provider_key":
      return {
        title: "Provider key needed",
        description: "Add a provider key in setup before AgentAway can plan or code.",
      };
    default:
      return {
        title: "Run in progress",
        description: `AgentAway is handling ${issue}.`,
      };
  }
}

function formatStatus(status: string) {
  return status
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function isStoppable(run: RunDetail) {
  if (run.cancellation_requested) {
    return false;
  }
  return !["planned", "failed", "draft_pr_opened", "needs_plan", "needs_provider_key", "unauthorized_actor"].includes(run.status);
}
