import Link from "next/link";
import { AuthActions } from "../components/AuthActions";
import { WorkbenchDashboard } from "../components/WorkbenchDashboard";

export default function Home() {
  return (
    <main className="shell">
      <div className="app-frame">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              AW
            </div>
            <div>
              <h1>AgentAway</h1>
              <p>GitHub issue workbench</p>
            </div>
          </div>
          <div className="topbar-actions">
            <Link className="nav-link" href="/runs">
              Runs
            </Link>
            <Link className="nav-link" href="/setup">
              Setup
            </Link>
            <AuthActions />
          </div>
        </header>

        <WorkbenchDashboard />
      </div>
    </main>
  );
}
