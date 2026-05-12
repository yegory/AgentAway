"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { NewIssueComposer } from "./NewIssueComposer";
import { useApiSession } from "../lib/useApiSession";
import { IssueSummary, RepositorySummary, RunSummary } from "../lib/workbenchTypes";

type RepoDetail = {
  repository: RepositorySummary;
  recent_runs: RunSummary[];
  latest_activity: Array<{
    id: number;
    event: string;
    action: string;
    sender_login: string;
    received_at: string;
    status: string;
  }>;
  command_shortcuts: Array<{ label: string; command: string }>;
};

type State =
  | { state: "loading" }
  | { state: "ok"; detail: RepoDetail; issues: IssueSummary[] }
  | { state: "error"; message: string };

export function RepositoryWorkbench({ repositoryId }: { repositoryId: string }) {
  const session = useApiSession();
  const [issueState, setIssueState] = useState<"open" | "closed">("open");
  const [showNewIssue, setShowNewIssue] = useState(false);
  const [data, setData] = useState<State>({ state: "loading" });

  async function load(state = issueState) {
    if (!session.ready || !session.signedIn) {
      return;
    }
    try {
      const [repoResponse, issuesResponse] = await Promise.all([
        session.fetchApi(`/api/repositories/${repositoryId}`),
        session.fetchApi(`/api/repositories/${repositoryId}/issues?state=${state}`),
      ]);
      const repoBody = await repoResponse.json();
      const issuesBody = await issuesResponse.json();
      if (!repoResponse.ok || !issuesResponse.ok) {
        setData({ state: "error", message: "Repository is unavailable." });
        return;
      }
      setData({ state: "ok", detail: repoBody, issues: issuesBody.issues ?? [] });
    } catch {
      setData({ state: "error", message: "API is unreachable." });
    }
  }

  useEffect(() => {
    load(issueState);
  }, [session.ready, session.signedIn, repositoryId, issueState]);

  if (!session.ready || data.state === "loading") {
    return <LoadingPanel />;
  }
  if (!session.signedIn) {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Sign in</span>
        <h2>Sign in to open this repository.</h2>
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

  const { detail, issues } = data;
  return (
    <div className="stack with-bottom-bar">
      <section className="panel stack">
        <div className="status-row">
          <div>
            <h2>{detail.repository.full_name}</h2>
            <p className="muted">{detail.repository.private ? "Private" : "Public"} repo on {detail.repository.default_branch}</p>
          </div>
          <a className="nav-link" href={`https://github.com/${detail.repository.full_name}`}>
            GitHub
          </a>
        </div>
        <div className="segmented" role="tablist" aria-label="Issue state">
          {(["open", "closed"] as const).map((state) => (
            <button
              aria-selected={issueState === state}
              className={issueState === state ? "active" : ""}
              key={state}
              onClick={() => setIssueState(state)}
              type="button"
            >
              {state}
            </button>
          ))}
        </div>
      </section>

      {showNewIssue ? (
        <section className="panel stack" id="new-issue">
          <div className="status-row">
            <h2>New issue</h2>
            <button className="nav-link" onClick={() => setShowNewIssue(false)} type="button">
              Close
            </button>
          </div>
          <NewIssueComposer repositoryId={Number(repositoryId)} />
        </section>
      ) : null}

      <section className="panel stack">
        <div className="status-row">
          <h2>Issues</h2>
          <button className="primary-action compact-action" onClick={() => setShowNewIssue(true)} type="button">
            New
          </button>
        </div>
        {issues.length === 0 ? (
          <p className="muted">No {issueState} issues returned from GitHub.</p>
        ) : (
          <div className="issue-list">
            {issues.map((issue) => (
              <Link
                className="issue-card"
                href={`/repos/${repositoryId}/issues/${issue.number}`}
                key={issue.id}
              >
                <div>
                  <strong>#{issue.number} {issue.title}</strong>
                  <span>{issue.user?.login || "unknown"} - {issue.comments} comments</span>
                </div>
                <span className={`pill ${issue.state === "closed" ? "warn" : ""}`}>{issue.state}</span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className="panel stack">
        <h2>Command shortcuts</h2>
        <div className="shortcut-grid">
          {detail.command_shortcuts.map((shortcut) => (
            <div className="shortcut" key={shortcut.label}>
              <span>{shortcut.label}</span>
              <code>{shortcut.command}</code>
            </div>
          ))}
        </div>
      </section>

      <section className="panel stack">
        <h2>Latest activity</h2>
        {detail.latest_activity.length === 0 ? (
          <p className="muted">No webhook activity recorded yet.</p>
        ) : (
          <div className="compact-list">
            {detail.latest_activity.map((activity) => (
              <div className="compact-row" key={activity.id}>
                <div>
                  <strong>{activity.event} {activity.action}</strong>
                  <span>{activity.sender_login || "GitHub"} - {new Date(activity.received_at).toLocaleString()}</span>
                </div>
                <span className="pill">{activity.status}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {detail.recent_runs.length ? (
        <section className="panel stack">
          <h2>Recent runs</h2>
          <div className="compact-list">
            {detail.recent_runs.map((run) => (
              <Link className="run-row" href={`/runs/${run.id}`} key={run.id}>
                <div>
                  <strong>#{run.issue_number ?? "?"} {run.issue_title || "Agent run"}</strong>
                  <span>/{run.command}</span>
                </div>
                <span className={`pill status-${run.status}`}>{run.status}</span>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <nav className="bottom-action-bar" aria-label="Repository actions">
        <button onClick={() => setShowNewIssue(true)} type="button">New issue</button>
        <button onClick={() => load(issueState)} type="button">Refresh</button>
        <Link href="/">Dashboard</Link>
      </nav>
    </div>
  );
}

function LoadingPanel() {
  return (
    <section className="panel empty-state">
      <span className="pill warn">Loading</span>
      <h2>Loading repository.</h2>
    </section>
  );
}
