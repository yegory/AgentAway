import Link from "next/link";
import { AuthActions } from "../../../components/AuthActions";
import { RepositoryWorkbench } from "../../../components/RepositoryWorkbench";

type RepoPageProps = {
  params: Promise<{ repoId: string }>;
};

export default async function RepoPage({ params }: RepoPageProps) {
  const { repoId } = await params;

  return (
    <main className="shell">
      <div className="app-frame">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              AW
            </div>
            <div>
              <h1>Repository</h1>
              <p>Issues, commands, and activity</p>
            </div>
          </div>
          <div className="topbar-actions">
            <Link className="nav-link" href="/">
              Home
            </Link>
            <AuthActions />
          </div>
        </header>

        <RepositoryWorkbench repositoryId={repoId} />
      </div>
    </main>
  );
}
