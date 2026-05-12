"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { CommandComposer } from "./CommandComposer";
import { AgentCommand } from "../lib/commands";
import { useApiSession } from "../lib/useApiSession";
import {
  IssueComment,
  IssueSummary,
  RepositorySummary,
  RunSummary,
} from "../lib/workbenchTypes";

type IssueDetail = {
  issue: IssueSummary;
  repository: RepositorySummary;
  related_runs: RunSummary[];
};

type State =
  | { state: "loading" }
  | { state: "ok"; detail: IssueDetail; comments: IssueComment[] }
  | { state: "error"; message: string };

export function IssueWorkbench({
  repositoryId,
  issueNumber,
}: {
  repositoryId: string;
  issueNumber: string;
}) {
  const session = useApiSession();
  const [data, setData] = useState<State>({ state: "loading" });
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState("");
  const [composerCommand, setComposerCommand] = useState<AgentCommand | null>(null);
  const [postingComment, setPostingComment] = useState(false);

  async function load() {
    if (!session.ready || !session.signedIn) {
      return;
    }
    try {
      const [issueResponse, commentsResponse] = await Promise.all([
        session.fetchApi(`/api/repositories/${repositoryId}/issues/${issueNumber}`),
        session.fetchApi(`/api/repositories/${repositoryId}/issues/${issueNumber}/comments`),
      ]);
      const issueBody = await issueResponse.json();
      const commentsBody = await commentsResponse.json();
      if (!issueResponse.ok || !commentsResponse.ok) {
        setData({ state: "error", message: "Issue is unavailable." });
        return;
      }
      setData({ state: "ok", detail: issueBody, comments: commentsBody.comments ?? [] });
    } catch {
      setData({ state: "error", message: "API is unreachable." });
    }
  }

  useEffect(() => {
    load();
  }, [session.ready, session.signedIn, repositoryId, issueNumber]);

  async function postComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!comment.trim()) {
      return;
    }
    setPostingComment(true);
    setMessage("Posting comment.");
    try {
      const response = await session.fetchApi(
        `/api/repositories/${repositoryId}/issues/${issueNumber}/comments`,
        {
          method: "POST",
          body: JSON.stringify({ body: comment }),
        },
      );
      setMessage(response.ok ? "Comment posted." : "Comment could not be posted.");
      if (response.ok) {
        setComment("");
        await load();
      }
    } catch {
      setMessage("API is unreachable.");
    } finally {
      setPostingComment(false);
    }
  }

  if (!session.ready || data.state === "loading") {
    return <LoadingPanel />;
  }
  if (!session.signedIn) {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Sign in</span>
        <h2>Sign in to open this issue.</h2>
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

  const { detail, comments } = data;
  return (
    <div className="stack with-bottom-bar">
      <section className="panel stack">
        <div className="status-row">
          <div>
            <h2>#{detail.issue.number} {detail.issue.title}</h2>
            <p className="muted">{detail.repository.full_name} - {detail.issue.user?.login || "unknown"}</p>
          </div>
          <span className={`pill ${detail.issue.state === "closed" ? "warn" : ""}`}>
            {detail.issue.state}
          </span>
        </div>
        {detail.issue.body ? <pre className="text-body">{detail.issue.body}</pre> : <p className="muted">No issue body.</p>}
        <div className="link-row">
          <a className="nav-link" href={detail.issue.html_url}>
            GitHub issue
          </a>
          <Link className="nav-link" href={`/repos/${repositoryId}`}>
            Repository
          </Link>
        </div>
      </section>

      <section className="panel stack">
        <h2>Agent commands</h2>
        <div className="command-button-grid">
          {(["plan", "fixplan", "proceed", "fix"] as AgentCommand[]).map((command) => (
            <button
              className={composerCommand === command ? "primary-action" : "nav-link"}
              key={command}
              onClick={() => setComposerCommand(command)}
              type="button"
            >
              {labelForCommand(command)}
            </button>
          ))}
        </div>
        {composerCommand ? (
          <CommandComposer
            initialCommand={composerCommand}
            issueNumber={Number(issueNumber)}
            onPosted={load}
            repositoryId={Number(repositoryId)}
          />
        ) : (
          <p className="muted">Choose a command to open the composer. Fix and Proceed require confirmation.</p>
        )}
      </section>

      <section className="panel stack">
        <h2>Comment</h2>
        <form className="stack" onSubmit={postComment}>
          <label>
            <span>Normal GitHub comment</span>
            <textarea
              onChange={(event) => setComment(event.target.value)}
              placeholder="Leave a note for collaborators."
              rows={4}
              value={comment}
            />
          </label>
          <div className="form-actions">
            <button className="primary-action" disabled={postingComment} type="submit">
              {postingComment ? "Posting" : "Post comment"}
            </button>
            {message ? <p className="muted">{message}</p> : null}
          </div>
        </form>
      </section>

      <section className="panel stack">
        <h2>Thread</h2>
        <div className="comment-list">
          {comments.length === 0 ? (
            <p className="muted">No comments yet.</p>
          ) : (
            comments.map((item) => (
              <article className="comment-card" key={item.id}>
                <div className="status-row">
                  <strong>{item.user?.login || "unknown"}</strong>
                  <a className="subtle-link" href={item.html_url}>
                    GitHub
                  </a>
                </div>
                <pre className="text-body">{item.body}</pre>
              </article>
            ))
          )}
        </div>
      </section>

      {detail.related_runs.length ? (
        <section className="panel stack">
          <h2>Runs for this issue</h2>
          <div className="compact-list">
            {detail.related_runs.map((run) => (
              <Link className="run-row" href={`/runs/${run.id}`} key={run.id}>
                <div>
                  <strong>Run #{run.id}</strong>
                  <span>/{run.command} - {new Date(run.updated_at).toLocaleString()}</span>
                </div>
                <span className={`pill status-${run.status}`}>{run.status}</span>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      {!composerCommand ? (
        <nav className="bottom-action-bar" aria-label="Issue actions">
          <button onClick={() => setComposerCommand("plan")} type="button">Plan</button>
          <button onClick={() => setComposerCommand("proceed")} type="button">Proceed</button>
          <button onClick={() => setComposerCommand("fix")} type="button">Fix</button>
        </nav>
      ) : null}
    </div>
  );
}

function labelForCommand(command: AgentCommand) {
  switch (command) {
    case "fixplan":
      return "Fix Plan";
    case "proceed":
      return "Proceed";
    case "fix":
      return "Fix";
    default:
      return "Plan";
  }
}

function LoadingPanel() {
  return (
    <section className="panel empty-state">
      <span className="pill warn">Loading</span>
      <h2>Loading issue.</h2>
    </section>
  );
}
