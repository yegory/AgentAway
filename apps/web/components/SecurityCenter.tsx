"use client";

import { UserProfile } from "@clerk/nextjs";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { CLERK_ENABLED } from "../lib/api";
import { API_SCOPE_COPY, countActiveTokens, nextScopeSelection } from "../lib/security";
import { useApiSession } from "../lib/useApiSession";

type TokenGrant = {
  id: number;
  label: string;
  token_family_id: string;
  scopes: string[];
  status: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  revoked_reason: string;
};

type AuditEvent = {
  id: number;
  action: string;
  target_type: string;
  target_id: string;
  payload_json: Record<string, unknown>;
  created_at: string | null;
};

type TokenState =
  | { state: "loading" }
  | {
      state: "ok";
      tokens: TokenGrant[];
      available_scopes: string[];
      default_scopes: string[];
      access_token_minutes: number;
      refresh_token_days: number;
    }
  | { state: "error"; message: string };

type AuditState =
  | { state: "loading" }
  | { state: "ok"; events: AuditEvent[] }
  | { state: "error"; message: string };

type Reveal = {
  access_token: string;
  refresh_token: string;
  access_token_expires_at: string;
  refresh_token_expires_at: string;
};

const SIGN_IN_METHODS = [
  "Email password",
  "Email code",
  "Email link",
  "GitHub OAuth",
  "Google OAuth",
  "Passkeys",
  "Authenticator app",
  "Backup codes",
];

type SecurityTab = "tokens" | "signin" | "audit" | "connections";

export function SecurityCenter() {
  const session = useApiSession();
  const [tab, setTab] = useState<SecurityTab>("tokens");
  const [tokens, setTokens] = useState<TokenState>({ state: "loading" });
  const [audit, setAudit] = useState<AuditState>({ state: "loading" });
  const [label, setLabel] = useState("Local CLI");
  const [selectedScopes, setSelectedScopes] = useState<string[]>([]);
  const [days, setDays] = useState(30);
  const [message, setMessage] = useState("");
  const [reveal, setReveal] = useState<Reveal | null>(null);
  const availableScopes = tokens.state === "ok" ? tokens.available_scopes : Object.keys(API_SCOPE_COPY);

  async function load() {
    if (!session.ready || !session.signedIn) {
      return;
    }
    try {
      const [tokenResponse, auditResponse] = await Promise.all([
        session.fetchApi("/api/auth/tokens"),
        session.fetchApi("/api/auth/audit"),
      ]);
      const tokenBody = await tokenResponse.json();
      const auditBody = await auditResponse.json();
      if (!tokenResponse.ok || !auditResponse.ok) {
        setTokens({ state: "error", message: "Security settings are unavailable." });
        setAudit({ state: "error", message: "Audit events are unavailable." });
        return;
      }
      setTokens({ state: "ok", ...tokenBody });
      setAudit({ state: "ok", events: auditBody.events ?? [] });
      if (selectedScopes.length === 0) {
        setSelectedScopes(tokenBody.default_scopes ?? []);
      }
    } catch {
      setTokens({ state: "error", message: "API is unreachable." });
      setAudit({ state: "error", message: "API is unreachable." });
    }
  }

  useEffect(() => {
    load();
  }, [session.ready, session.signedIn]);

  const activeTokenCount = useMemo(() => {
    if (tokens.state !== "ok") {
      return 0;
    }
    return countActiveTokens(tokens.tokens);
  }, [tokens]);

  function toggleScope(scope: string) {
    setSelectedScopes((current) => nextScopeSelection(current, scope));
  }

  async function createToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("Creating token.");
    setReveal(null);
    try {
      const response = await session.fetchApi("/api/auth/tokens", {
        method: "POST",
        body: JSON.stringify({
          label,
          scopes: selectedScopes,
          refresh_expires_in_days: days,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        setMessage(body.detail || "Token could not be created.");
        return;
      }
      setReveal({
        access_token: body.access_token,
        refresh_token: body.refresh_token,
        access_token_expires_at: body.access_token_expires_at,
        refresh_token_expires_at: body.refresh_token_expires_at,
      });
      setMessage("Token created.");
      await load();
    } catch {
      setMessage("API is unreachable.");
    }
  }

  async function revokeToken(tokenId: number) {
    setMessage("Revoking token.");
    try {
      const response = await session.fetchApi(`/api/auth/tokens/${tokenId}`, { method: "DELETE" });
      setMessage(response.ok ? "Token revoked." : "Token could not be revoked.");
      await load();
    } catch {
      setMessage("API is unreachable.");
    }
  }

  if (!session.ready) {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Loading</span>
        <h2>Security Center</h2>
      </section>
    );
  }
  if (!session.signedIn) {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Sign in</span>
        <h2>Security Center</h2>
      </section>
    );
  }

  return (
    <section className="panel stack security-center">
      <div className="status-row">
        <div>
          <h2>Security Center</h2>
          <p className="muted">{activeTokenCount} active API tokens</p>
        </div>
        <span className="pill">Scoped access</span>
      </div>

      <div className="security-tabs" role="tablist" aria-label="Security center">
        {(["tokens", "signin", "audit", "connections"] as SecurityTab[]).map((item) => (
          <button
            aria-selected={tab === item}
            className={tab === item ? "active" : ""}
            key={item}
            onClick={() => setTab(item)}
            type="button"
          >
            {tabLabel(item)}
          </button>
        ))}
      </div>

      {tab === "tokens" ? (
        <div className="security-layout">
          <form className="token-form" onSubmit={createToken}>
            <label>
              <span>Label</span>
              <input value={label} onChange={(event) => setLabel(event.target.value)} />
            </label>
            <label>
              <span>Refresh expiry</span>
              <input
                max={90}
                min={1}
                onChange={(event) => setDays(Number(event.target.value))}
                type="number"
                value={days}
              />
            </label>
            <div className="scope-grid">
              {availableScopes.map((scope) => {
                const copy = API_SCOPE_COPY[scope] ?? { label: scope, description: "Custom scope" };
                return (
                  <label className="scope-card" key={scope}>
                    <input
                      checked={selectedScopes.includes(scope)}
                      onChange={() => toggleScope(scope)}
                      type="checkbox"
                    />
                    <span>
                      <strong>{copy.label}</strong>
                      <small>{scope}</small>
                    </span>
                  </label>
                );
              })}
            </div>
            <div className="form-actions">
              <button className="primary-action" type="submit">
                Create token
              </button>
              {message ? <p className="muted">{message}</p> : null}
            </div>
            {reveal ? <TokenReveal reveal={reveal} /> : null}
          </form>

          <TokenList state={tokens} onRevoke={revokeToken} />
        </div>
      ) : null}

      {tab === "signin" ? <SignInSecurity /> : null}
      {tab === "audit" ? <AuditList state={audit} /> : null}
      {tab === "connections" ? <ConnectionSecurity /> : null}
    </section>
  );
}

function TokenReveal({ reveal }: { reveal: Reveal }) {
  return (
    <div className="token-reveal">
      <div className="status-row">
        <strong>One-time token values</strong>
        <span className="pill warn">Store now</span>
      </div>
      <SecretBlock label="Access token" value={reveal.access_token} expiresAt={reveal.access_token_expires_at} />
      <SecretBlock label="Refresh token" value={reveal.refresh_token} expiresAt={reveal.refresh_token_expires_at} />
    </div>
  );
}

function SecretBlock({ label, value, expiresAt }: { label: string; value: string; expiresAt: string }) {
  async function copy() {
    await navigator.clipboard?.writeText(value);
  }

  return (
    <div className="token-secret">
      <div className="status-row">
        <span>{label}</span>
        <button className="nav-link compact-action" onClick={copy} type="button">
          Copy
        </button>
      </div>
      <code>{value}</code>
      <small>Expires {new Date(expiresAt).toLocaleString()}</small>
    </div>
  );
}

function TokenList({
  state,
  onRevoke,
}: {
  state: TokenState;
  onRevoke: (tokenId: number) => void;
}) {
  if (state.state === "loading") {
    return <p className="muted">Loading API tokens.</p>;
  }
  if (state.state === "error") {
    return <p className="muted">{state.message}</p>;
  }
  if (!state.tokens.length) {
    return (
      <div className="empty-state">
        <span className="pill warn">No tokens</span>
        <h3>External API access is off.</h3>
      </div>
    );
  }

  return (
    <div className="token-list">
      {state.tokens.map((token) => (
        <article className="api-token-card" key={token.id}>
          <div className="status-row">
            <div>
              <strong>{token.label}</strong>
              <span>{token.token_family_id}</span>
            </div>
            <span className={`pill ${token.status !== "active" ? "warn" : ""}`}>{token.status}</span>
          </div>
          <div className="file-list">
            {token.scopes.map((scope) => (
              <code key={scope}>{scope}</code>
            ))}
          </div>
          <small>
            Last used {token.last_used_at ? new Date(token.last_used_at).toLocaleString() : "never"} · Expires{" "}
            {token.expires_at ? new Date(token.expires_at).toLocaleDateString() : "never"}
          </small>
          {token.status === "active" ? (
            <button className="nav-link compact-action" onClick={() => onRevoke(token.id)} type="button">
              Revoke
            </button>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function SignInSecurity() {
  return (
    <div className="stack">
      <div className="method-grid">
        {SIGN_IN_METHODS.map((method) => (
          <div className="method-card" key={method}>
            <strong>{method}</strong>
            <span>{method === "Passkeys" ? "WebAuthn" : method.includes("OAuth") ? "OIDC" : "Clerk"}</span>
          </div>
        ))}
      </div>
      {CLERK_ENABLED ? (
        <div className="clerk-profile-frame">
          <UserProfile routing="hash" />
        </div>
      ) : (
        <div className="empty-state">
          <span className="pill warn">Dev auth</span>
          <h3>Clerk is not configured locally.</h3>
        </div>
      )}
    </div>
  );
}

function AuditList({ state }: { state: AuditState }) {
  if (state.state === "loading") {
    return <p className="muted">Loading audit events.</p>;
  }
  if (state.state === "error") {
    return <p className="muted">{state.message}</p>;
  }
  if (!state.events.length) {
    return <p className="muted">No audit events recorded yet.</p>;
  }
  return (
    <div className="audit-list">
      {state.events.map((event) => (
        <article className="timeline-item" key={event.id}>
          <span>{event.created_at ? new Date(event.created_at).toLocaleString() : "unknown time"}</span>
          <strong>{event.action.replaceAll("_", " ")}</strong>
          <p>
            {event.target_type || "account"} {event.target_id}
          </p>
        </article>
      ))}
    </div>
  );
}

function ConnectionSecurity() {
  return (
    <div className="method-grid">
      <div className="method-card">
        <strong>GitHub App</strong>
        <span>Installation tokens</span>
      </div>
      <div className="method-card">
        <strong>Provider keys</strong>
        <span>Encrypted BYOK</span>
      </div>
      <div className="method-card">
        <strong>Webhooks</strong>
        <span>HMAC SHA-256</span>
      </div>
      <div className="method-card">
        <strong>Agent writes</strong>
        <span>Draft PR only</span>
      </div>
    </div>
  );
}

function tabLabel(tab: SecurityTab) {
  switch (tab) {
    case "signin":
      return "Sign-in";
    case "audit":
      return "Audit";
    case "connections":
      return "Connections";
    default:
      return "API tokens";
  }
}
