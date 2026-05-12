import Link from "next/link";
import { AuthActions } from "../../../../../components/AuthActions";
import { IssueWorkbench } from "../../../../../components/IssueWorkbench";

type IssuePageProps = {
  params: Promise<{ repoId: string; issueNumber: string }>;
};

export default async function IssuePage({ params }: IssuePageProps) {
  const { repoId, issueNumber } = await params;

  return (
    <main className="shell">
      <div className="app-frame">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              AW
            </div>
            <div>
              <h1>Issue #{issueNumber}</h1>
              <p>Comment and agent controls</p>
            </div>
          </div>
          <div className="topbar-actions">
            <Link className="nav-link" href={`/repos/${repoId}`}>
              Repo
            </Link>
            <AuthActions />
          </div>
        </header>

        <IssueWorkbench issueNumber={issueNumber} repositoryId={repoId} />
      </div>
    </main>
  );
}
