import Link from "next/link";
import { AuthActions } from "../../../components/AuthActions";
import { GitHubInstallCallback } from "../../../components/GitHubInstallCallback";

type GitHubCallbackProps = {
  searchParams: Promise<{ installation_id?: string }>;
};

export default async function GitHubCallback({ searchParams }: GitHubCallbackProps) {
  const params = await searchParams;

  return (
    <main className="shell">
      <div className="app-frame">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              AW
            </div>
            <div>
              <h1>GitHub setup</h1>
              <p>Linking your GitHub App installation.</p>
            </div>
          </div>
          <div className="topbar-actions">
            <Link className="nav-link" href="/">
              Home
            </Link>
            <AuthActions />
          </div>
        </header>

        <GitHubInstallCallback installationId={params.installation_id ?? null} />
      </div>
    </main>
  );
}
