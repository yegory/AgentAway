"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, CLERK_ENABLED } from "../lib/api";

type AgentRun = {
  id: number;
  repository: { full_name: string } | null;
  issue_number: number | null;
  issue_title: string;
  trigger_actor: string;
  command: string;
  status: string;
  pull_request_url: string;
  created_at: string;
};

type RunListState =
  | { state: "loading" }
  | { state: "ok"; runs: AgentRun[] }
  | { state: "error"; message: string };

export function RunList() {
  if (CLERK_ENABLED) {
    return <ClerkRunList />;
  }
  return <RunListInner />;
}

function ClerkRunList() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) {
    return <RunListLoading />;
  }
  if (!isSignedIn) {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Sign in</span>
        <h2>Sign in to view your run inbox.</h2>
      </section>
    );
  }
  return <RunListInner getToken={getToken} />;
}

function RunListInner({ getToken }: { getToken?: () => Promise<string | null> }) {
  const [data, setData] = useState<RunListState>({ state: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function loadRuns() {
      try {
        const response = await apiFetch("/api/runs", {
          token: getToken ? await getToken() : null,
        });
        const body = await response.json();

        if (cancelled) {
          return;
        }

        if (!response.ok) {
          setData({ state: "error", message: "Run inbox is unavailable." });
          return;
        }

        setData({ state: "ok", runs: body.runs ?? [] });
      } catch {
        if (!cancelled) {
          setData({ state: "error", message: "API is unreachable." });
        }
      }
    }

    loadRuns();

    return () => {
      cancelled = true;
    };
  }, []);

  if (data.state === "loading") {
    return <RunListLoading />;
  }

  if (data.state === "error") {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Offline</span>
        <h2>{data.message}</h2>
      </section>
    );
  }

  if (data.runs.length === 0) {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Empty</span>
        <h2>No agent runs yet.</h2>
        <p>Signed GitHub issue comments will create runs here.</p>
      </section>
    );
  }

  return (
    <section className="stack">
      {data.runs.map((run) => (
        <article className="panel stack" key={run.id}>
          <div className="status-row">
            <h2>Issue #{run.issue_number ?? "unknown"}</h2>
            <span className="pill">{run.status}</span>
          </div>
          <p className="muted">{run.issue_title || run.repository?.full_name || "GitHub issue command"}</p>
          <div className="meta-grid">
            <div className="metric">
              <span>Command</span>
              <strong>/{run.command}</strong>
            </div>
            <div className="metric">
              <span>Actor</span>
              <strong>{run.trigger_actor || "unknown"}</strong>
            </div>
            <div className="metric">
              <span>Run</span>
              <strong>#{run.id}</strong>
            </div>
          </div>
          <div className="status-row">
            <Link className="nav-link" href={`/runs/${run.id}`}>
              Details
            </Link>
            {run.pull_request_url ? (
              <a className="nav-link" href={run.pull_request_url}>
                Draft PR
              </a>
            ) : null}
          </div>
        </article>
      ))}
    </section>
  );
}

function RunListLoading() {
  return (
    <section className="panel empty-state">
      <span className="pill warn">Loading</span>
      <h2>Checking run inbox.</h2>
    </section>
  );
}
