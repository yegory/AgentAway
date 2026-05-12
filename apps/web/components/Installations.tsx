"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import { apiFetch, CLERK_ENABLED } from "../lib/api";

type Repository = {
  id: number;
  full_name: string;
  default_branch: string;
};

type Installation = {
  id: number;
  github_installation_id: number;
  account_login: string;
  repositories: Repository[];
};

type InstallationState =
  | { state: "loading" }
  | { state: "ok"; installations: Installation[]; install_url: string }
  | { state: "error"; message: string };

export function Installations() {
  if (CLERK_ENABLED) {
    return <ClerkInstallations />;
  }
  return <InstallationsInner />;
}

function ClerkInstallations() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) {
    return <InstallationShell state={{ state: "loading" }} />;
  }
  if (!isSignedIn) {
    return null;
  }
  return <InstallationsInner getToken={getToken} />;
}

function InstallationsInner({ getToken }: { getToken?: () => Promise<string | null> }) {
  const [data, setData] = useState<InstallationState>({ state: "loading" });

  async function load() {
    try {
      const response = await apiFetch("/api/installations", {
        token: getToken ? await getToken() : null,
      });
      const body = await response.json();
      setData(response.ok ? { state: "ok", installations: body.installations ?? [], install_url: body.install_url ?? "" } : { state: "error", message: "Installations are unavailable." });
    } catch {
      setData({ state: "error", message: "API is unreachable." });
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <section className="panel stack">
      <div className="status-row">
        <h2>GitHub App</h2>
        {data.state === "loading" ? (
          <span className="pill warn">Loading</span>
        ) : data.state === "ok" && data.install_url ? (
          <a className="nav-link" href={data.install_url}>
            Install
          </a>
        ) : (
          <span className="pill warn">Set slug</span>
        )}
      </div>
      <InstallationShell state={data} />
    </section>
  );
}

function InstallationShell({ state }: { state: InstallationState }) {
  if (state.state === "loading") {
    return <p className="muted">Loading GitHub installations.</p>;
  }
  if (state.state === "error") {
    return <p className="muted">{state.message}</p>;
  }
  if (state.installations.length === 0) {
    return <p className="muted">No GitHub App installations linked yet.</p>;
  }

  return (
    <div className="stack">
      {state.installations.map((installation) => (
        <div className="metric metric-wide" key={installation.github_installation_id}>
          <span>{installation.account_login || `installation ${installation.github_installation_id}`}</span>
          <strong>{installation.repositories.length} repositories</strong>
          <small>{installation.repositories.map((repo) => repo.full_name).join(", ") || "Waiting for repository sync"}</small>
        </div>
      ))}
    </div>
  );
}
