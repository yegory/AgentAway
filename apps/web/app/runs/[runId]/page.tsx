import Link from "next/link";
import { AuthActions } from "../../../components/AuthActions";
import { RunDetailClient } from "../../../components/RunDetailClient";

type RunDetailProps = {
  params: Promise<{ runId: string }>;
};

export default async function RunDetail({ params }: RunDetailProps) {
  const { runId } = await params;

  return (
    <main className="shell">
      <div className="app-frame">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              AW
            </div>
            <div>
              <h1>Run {runId}</h1>
              <p>Plan, timeline, and next actions</p>
            </div>
          </div>
          <div className="topbar-actions">
            <Link className="nav-link" href="/runs">
              Back
            </Link>
            <AuthActions />
          </div>
        </header>

        <RunDetailClient runId={runId} />
      </div>
    </main>
  );
}
