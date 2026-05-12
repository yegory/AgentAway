"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "../lib/api";

type HealthState =
  | { state: "loading" }
  | { state: "ok"; postgres: string; redis: string }
  | { state: "error"; message: string };

export function SystemStatus() {
  const [health, setHealth] = useState<HealthState>({ state: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      try {
        const response = await fetch(apiUrl("/health"), { cache: "no-store" });
        const body = await response.json();

        if (cancelled) {
          return;
        }

        if (!response.ok) {
          setHealth({ state: "error", message: "API is not healthy yet." });
          return;
        }

        setHealth({
          state: "ok",
          postgres: body.dependencies?.postgres ?? "unknown",
          redis: body.dependencies?.redis ?? "unknown",
        });
      } catch {
        if (!cancelled) {
          setHealth({ state: "error", message: "API is unreachable." });
        }
      }
    }

    loadHealth();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="panel stack" aria-live="polite">
      <div className="status-row">
        <h3>Local system</h3>
        {health.state === "ok" ? (
          <span className="pill">Healthy</span>
        ) : (
          <span className="pill warn">
            {health.state === "loading" ? "Checking" : "Needs API"}
          </span>
        )}
      </div>

      {health.state === "ok" ? (
        <div className="meta-grid">
          <div className="metric">
            <span>Postgres</span>
            <strong>{health.postgres}</strong>
          </div>
          <div className="metric">
            <span>Redis</span>
            <strong>{health.redis}</strong>
          </div>
          <div className="metric">
            <span>API</span>
            <strong>ok</strong>
          </div>
        </div>
      ) : (
        <p className="muted">
          {health.state === "loading"
            ? "Checking FastAPI health."
            : health.message}
        </p>
      )}
    </section>
  );
}
