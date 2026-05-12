import Link from "next/link";
import { AuthActions } from "../../components/AuthActions";
import { Installations } from "../../components/Installations";
import { ProviderKeys } from "../../components/ProviderKeys";
import { SecurityCenter } from "../../components/SecurityCenter";
import { SystemStatus } from "../../components/SystemStatus";

export default function SetupPage() {
  return (
    <main className="shell">
      <div className="app-frame">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              AW
            </div>
            <div>
              <h1>Setup</h1>
              <p>Provider keys and GitHub App link</p>
            </div>
          </div>
          <div className="topbar-actions">
            <Link className="nav-link" href="/">
              Workbench
            </Link>
            <AuthActions />
          </div>
        </header>

        <div className="stack">
          <SecurityCenter />
          <div className="setup-grid">
          <SystemStatus />
          <ProviderKeys />
          <Installations />
          </div>
        </div>
      </div>
    </main>
  );
}
