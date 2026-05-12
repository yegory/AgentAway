"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, CLERK_ENABLED } from "../lib/api";

export function GitHubInstallCallback({ installationId }: { installationId: string | null }) {
  if (CLERK_ENABLED) {
    return <ClerkGitHubInstallCallback installationId={installationId} />;
  }
  return <GitHubInstallCallbackInner installationId={installationId} />;
}

function ClerkGitHubInstallCallback({ installationId }: { installationId: string | null }) {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) {
    return <CallbackPanel status="Linking installation." />;
  }
  if (!isSignedIn) {
    return <CallbackPanel status="Sign in, then return to this callback URL." warn />;
  }
  return <GitHubInstallCallbackInner installationId={installationId} getToken={getToken} />;
}

function GitHubInstallCallbackInner({
  installationId,
  getToken,
}: {
  installationId: string | null;
  getToken?: () => Promise<string | null>;
}) {
  const [status, setStatus] = useState("Linking installation.");
  const [warn, setWarn] = useState(false);

  useEffect(() => {
    async function link() {
      if (!installationId) {
        setWarn(true);
        setStatus("GitHub did not include an installation id.");
        return;
      }

      const response = await apiFetch("/api/github/installations/link", {
        method: "POST",
        token: getToken ? await getToken() : null,
        body: JSON.stringify({ installation_id: Number(installationId) }),
      });
      setWarn(!response.ok);
      setStatus(response.ok ? "GitHub installation linked." : "Could not link the GitHub installation.");
    }
    link();
  }, [installationId]);

  return <CallbackPanel status={status} warn={warn} />;
}

function CallbackPanel({ status, warn = false }: { status: string; warn?: boolean }) {
  return (
    <section className="panel empty-state">
      <span className={warn ? "pill warn" : "pill"}>{warn ? "Check setup" : "Connected"}</span>
      <h2>{status}</h2>
      <Link className="primary-action" href="/">
        Back to setup
      </Link>
    </section>
  );
}
