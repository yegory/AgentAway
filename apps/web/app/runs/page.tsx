import Link from "next/link";
import { AuthActions } from "../../components/AuthActions";
import { RunList } from "../../components/RunList";

export default function RunsPage() {
  return (
    <main className="shell">
      <div className="app-frame">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              AW
            </div>
            <div>
              <h1>Run Inbox</h1>
              <p>Recent agent work across repositories</p>
            </div>
          </div>
          <div className="topbar-actions">
            <Link className="nav-link" href="/">
              Home
            </Link>
            <AuthActions />
          </div>
        </header>

        <RunList />
      </div>
    </main>
  );
}
