"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useApiSession } from "../lib/useApiSession";
import {
  InstallationSummary,
  RepositorySummary,
  RunSummary,
} from "../lib/workbenchTypes";

type DashboardState =
  | { state: "loading" }
  | {
      state: "ok";
      installations: InstallationSummary[];
      repositories: RepositorySummary[];
      recent_runs: RunSummary[];
      setup_warnings: Array<{ code: string; message: string }>;
      last_webhook_at: string | null;
      install_url: string;
    }
  | { state: "error"; message: string };

export function WorkbenchDashboard() {
  const session = useApiSession();
  const [data, setData] = useState<DashboardState>({ state: "loading" });

  async function load() {
    if (!session.ready || !session.signedIn) {
      return;
    }
    try {
      const response = await session.fetchApi("/api/workbench");
      const body = await response.json();
      setData(response.ok ? { state: "ok", ...body } : { state: "error", message: "Workbench is unavailable." });
    } catch {
      setData({ state: "error", message: "API is unreachable." });
    }
  }

  useEffect(() => {
    load();
  }, [session.ready, session.signedIn]);

  if (!session.ready) {
    return <WorkbenchLoading />;
  }
  if (!session.signedIn) {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Sign in</span>
        <h2>Open your GitHub issue workbench.</h2>
        <p>The first screen after login is the repo control surface.</p>
      </section>
    );
  }
  if (data.state === "loading") {
    return <WorkbenchLoading />;
  }
  if (data.state === "error") {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Offline</span>
        <h2>{data.message}</h2>
      </section>
    );
  }

  return (
    <div className="stack with-bottom-bar">
      {data.setup_warnings.length ? (
        <section className="panel stack">
          <div className="status-row">
            <h2>Setup checks</h2>
            <span className="pill warn">{data.setup_warnings.length} warnings</span>
          </div>
          <div className="warning-list">
            {data.setup_warnings.map((warning) => (
              <div className="warning-row" key={warning.code}>
                <strong>{warning.code.replaceAll("_", " ")}</strong>
                <span>{warning.message}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="panel stack">
        <div className="status-row">
          <h2>Repositories</h2>
          {data.install_url ? (
            <a className="nav-link" href={data.install_url}>
              Install
            </a>
          ) : (
            <span className="pill warn">Set app slug</span>
          )}
        </div>
        {data.repositories.length === 0 ? (
          <p className="muted">No repositories synced yet. Link an installation, then wait for GitHub to send repository data.</p>
        ) : (
          <div className="repo-grid">
            {data.repositories.map((repository) => (
              <Link className="repo-card" href={`/repos/${repository.id}`} key={repository.id}>
                <span>{repository.private ? "Private" : "Public"}</span>
                <strong>{repository.full_name}</strong>
                <small>{repository.default_branch}</small>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className="panel stack">
        <div className="status-row">
          <h2>GitHub App</h2>
          <span className="pill">{data.installations.length} linked</span>
        </div>
        {data.installations.length === 0 ? (
          <p className="muted">No installations linked to this account.</p>
        ) : (
          <div className="compact-list">
            {data.installations.map((installation) => (
              <div className="compact-row" key={installation.github_installation_id}>
                <div>
                  <strong>{installation.account_login || `installation ${installation.github_installation_id}`}</strong>
                  <span>{installation.account_type || "GitHub account"}</span>
                </div>
                <span className="pill">{installation.repositories.length} repos</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel stack">
        <div className="status-row">
          <h2>Recent runs</h2>
          <Link className="nav-link" href="/runs">
            All
          </Link>
        </div>
        {data.recent_runs.length === 0 ? (
          <p className="muted">No agent runs yet. Open an issue and post a command.</p>
        ) : (
          <div className="compact-list">
            {data.recent_runs.map((run) => (
              <Link className="run-row" href={`/runs/${run.id}`} key={run.id}>
                <div>
                  <strong>#{run.issue_number ?? "?"} {run.issue_title || run.repository?.full_name || "GitHub issue"}</strong>
                  <span>/{run.command} by {run.trigger_actor || "unknown"}</span>
                </div>
                <span className={`pill status-${run.status}`}>{run.status}</span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <nav className="bottom-action-bar" aria-label="Workbench actions">
        <Link href="/runs">Runs</Link>
        {data.repositories[0] ? <Link href={`/repos/${data.repositories[0].id}`}>First repo</Link> : null}
        <Link href="/setup">Setup</Link>
      </nav>
    </div>
  );
}

function WorkbenchLoading() {
  return (
    <section className="panel empty-state">
      <span className="pill warn">Loading</span>
      <h2>Opening workbench.</h2>
    </section>
  );
}
