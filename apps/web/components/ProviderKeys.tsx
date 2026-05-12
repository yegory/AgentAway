"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, CLERK_ENABLED } from "../lib/api";

type ProviderKey = {
  provider: string;
  key_hint: string;
  model_name: string;
  base_url: string;
  status: string;
};

type ProviderKeyState =
  | { state: "loading" }
  | { state: "ok"; provider_keys: ProviderKey[]; default_provider: string | null }
  | { state: "error"; message: string };

const PROVIDERS = [
  { id: "deepseek", label: "DeepSeek", model: "deepseek-v4-flash", baseUrl: "https://api.deepseek.com" },
  { id: "openai", label: "OpenAI", model: "gpt-4.1-mini", baseUrl: "https://api.openai.com" },
  { id: "anthropic", label: "Anthropic", model: "claude-sonnet-4-5", baseUrl: "https://api.anthropic.com" },
];

export function ProviderKeys() {
  if (CLERK_ENABLED) {
    return <ClerkProviderKeys />;
  }
  return <ProviderKeysInner />;
}

function ClerkProviderKeys() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) {
    return <ProviderKeyShell state={{ state: "loading" }} />;
  }
  if (!isSignedIn) {
    return (
      <section className="panel empty-state">
        <span className="pill warn">Sign in</span>
        <h2>Connect your account to store provider keys.</h2>
      </section>
    );
  }
  return <ProviderKeysInner getToken={getToken} />;
}

function ProviderKeysInner({ getToken }: { getToken?: () => Promise<string | null> }) {
  const [data, setData] = useState<ProviderKeyState>({ state: "loading" });
  const [provider, setProvider] = useState(PROVIDERS[0].id);
  const selected = PROVIDERS.find((item) => item.id === provider) ?? PROVIDERS[0];
  const [modelName, setModelName] = useState(selected.model);
  const [baseUrl, setBaseUrl] = useState(selected.baseUrl);
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState("");

  async function token() {
    return getToken ? getToken() : null;
  }

  async function load() {
    try {
      const response = await apiFetch("/api/provider-keys", { token: await token() });
      const body = await response.json();
      setData(response.ok ? { state: "ok", ...body } : { state: "error", message: "Provider keys are unavailable." });
    } catch {
      setData({ state: "error", message: "API is unreachable." });
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    setModelName(selected.model);
    setBaseUrl(selected.baseUrl);
  }, [provider]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("Saving key.");
    const response = await apiFetch("/api/provider-keys", {
      method: "POST",
      token: await token(),
      body: JSON.stringify({
        provider,
        api_key: apiKey,
        model_name: modelName,
        base_url: baseUrl,
        make_default: true,
      }),
    });
    setMessage(response.ok ? "Provider key saved." : "Provider key could not be saved.");
    setApiKey("");
    await load();
  }

  return (
    <section className="panel stack">
      <div className="status-row">
        <h2>Provider keys</h2>
        <span className="pill">Encrypted BYOK</span>
      </div>
      <ProviderKeyShell state={data} />
      <form className="form-grid" onSubmit={submit}>
        <label>
          <span>Provider</span>
          <select value={provider} onChange={(event) => setProvider(event.target.value)}>
            {PROVIDERS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Model</span>
          <input value={modelName} onChange={(event) => setModelName(event.target.value)} />
        </label>
        <label>
          <span>Base URL</span>
          <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
        </label>
        <label className="form-wide">
          <span>API key</span>
          <input
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="Stored encrypted server-side"
            type="password"
            required
          />
        </label>
        <button className="primary-action" type="submit">
          Save key
        </button>
        {message ? <p className="muted">{message}</p> : null}
      </form>
    </section>
  );
}

function ProviderKeyShell({ state }: { state: ProviderKeyState }) {
  if (state.state === "loading") {
    return <p className="muted">Loading provider keys.</p>;
  }
  if (state.state === "error") {
    return <p className="muted">{state.message}</p>;
  }
  if (state.provider_keys.length === 0) {
    return <p className="muted">No provider keys saved yet.</p>;
  }
  return (
    <div className="meta-grid">
      {state.provider_keys.map((key) => (
        <div className="metric" key={key.provider}>
          <span>{key.provider}</span>
          <strong>{key.key_hint}</strong>
          <small>{key.model_name}</small>
        </div>
      ))}
    </div>
  );
}
