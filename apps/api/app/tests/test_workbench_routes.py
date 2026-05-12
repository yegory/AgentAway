import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, GitHubInstallation, Repository, RepositoryAccess, UserAccount
from app.routes import workbench
from app.services.auth import AuthenticatedUser


class WorkbenchRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.session: Session = self.SessionLocal()

        self.account = UserAccount(clerk_user_id="user_1", email="dev@example.com")
        self.installation = GitHubInstallation(
            user=self.account,
            github_installation_id=12345,
            account_login="agentaway",
            account_type="Organization",
        )
        self.repository = Repository(
            installation=self.installation,
            github_repo_id=99,
            owner="agentaway",
            name="demo",
            full_name="agentaway/demo",
            default_branch="main",
        )
        self.session.add_all([self.account, self.installation, self.repository])
        self.session.flush()
        self.session.add(
            RepositoryAccess(
                user_id=self.account.id,
                repository_id=self.repository.id,
                role="admin",
            )
        )
        self.session.commit()

        app = FastAPI()
        app.include_router(workbench.router)

        def override_session():
            yield self.session

        def override_user():
            return AuthenticatedUser(account=self.account, claims={"sub": "user_1"}, is_dev=True)

        app.dependency_overrides[workbench.get_session] = override_session
        app.dependency_overrides[workbench.get_current_user] = override_user
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_list_repositories_returns_only_accessible_repos(self) -> None:
        other_repo = Repository(
            github_repo_id=100,
            owner="other",
            name="secret",
            full_name="other/secret",
        )
        self.session.add(other_repo)
        self.session.commit()

        with patch.object(workbench.github_client, "github_app_configured", return_value=False):
            response = self.client.get("/api/repositories")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([repo["full_name"] for repo in body["repositories"]], ["agentaway/demo"])

    def test_workbench_dedupes_repositories_and_exposes_install_url(self) -> None:
        duplicate = Repository(
            installation=self.installation,
            github_repo_id=101,
            owner="agentaway",
            name="demo",
            full_name="agentaway/demo",
            default_branch="main",
        )
        self.session.add(duplicate)
        self.session.flush()
        self.session.add(
            RepositoryAccess(
                user_id=self.account.id,
                repository_id=duplicate.id,
                role="admin",
            )
        )
        self.session.commit()

        old_slug = workbench.settings.github_app_slug
        workbench.settings.github_app_slug = "agentaway-app"
        try:
            with patch.object(workbench.github_client, "github_app_configured", return_value=False):
                response = self.client.get("/api/workbench")
        finally:
            workbench.settings.github_app_slug = old_slug

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["install_url"], "https://github.com/apps/agentaway-app/installations/new")
        self.assertEqual([repo["full_name"] for repo in body["repositories"]], ["agentaway/demo"])
        self.assertEqual(
            [repo["full_name"] for repo in body["installations"][0]["repositories"]],
            ["agentaway/demo"],
        )

    def test_issue_list_uses_installation_token_server_side(self) -> None:
        seen: dict[str, object] = {}

        def fake_list_issues(token: str, full_name: str, state: str):
            seen["token"] = token
            seen["full_name"] = full_name
            seen["state"] = state
            return [
                {"id": 1, "number": 7, "title": "Bug", "state": "open", "user": {"login": "octo"}},
            ]

        with (
            patch.object(workbench.github_client, "installation_token", return_value=SimpleNamespace(token="server-token")),
            patch.object(workbench.github_client, "list_issues", side_effect=fake_list_issues),
        ):
            response = self.client.get(f"/api/repositories/{self.repository.id}/issues?state=open")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen, {"token": "server-token", "full_name": "agentaway/demo", "state": "open"})
        self.assertEqual(response.json()["issues"][0]["number"], 7)

    def test_repository_access_is_required_before_github_calls(self) -> None:
        with patch.object(workbench.github_client, "installation_token") as token_mock:
            response = self.client.get("/api/repositories/999/issues?state=open")

        self.assertEqual(response.status_code, 404)
        token_mock.assert_not_called()

    def test_high_risk_command_requires_confirmation(self) -> None:
        with patch.object(workbench.github_client, "create_issue_comment") as comment_mock:
            response = self.client.post(
                f"/api/repositories/{self.repository.id}/issues/7/commands",
                json={"command": "fix", "constraints": ["add tests"]},
            )

        self.assertEqual(response.status_code, 409)
        comment_mock.assert_not_called()

    def test_command_comment_posts_valid_command(self) -> None:
        posted: dict[str, object] = {}

        def fake_comment(token: str, full_name: str, issue_number: int, body: str):
            posted["token"] = token
            posted["full_name"] = full_name
            posted["issue_number"] = issue_number
            posted["body"] = body
            return {"id": 10, "body": body, "html_url": "https://github.com/agentaway/demo/issues/7#comment"}

        with (
            patch.object(workbench.github_client, "installation_token", return_value=SimpleNamespace(token="server-token")),
            patch.object(workbench.github_client, "get_issue", return_value={"id": 1, "number": 7, "title": "Bug", "body": "", "html_url": "https://github.com/agentaway/demo/issues/7"}),
            patch.object(workbench.github_client, "create_issue_comment", side_effect=fake_comment),
            patch.object(workbench, "enqueue_agent_run", return_value="task-1"),
        ):
            response = self.client.post(
                f"/api/repositories/{self.repository.id}/issues/7/commands",
                json={"command": "plan", "constraints": ["add tests", "max 2 files"]},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(posted["body"], "/plan add tests max 2 files")
        self.assertEqual(response.json()["command"]["command"], "plan")
        self.assertTrue(response.json()["agent_run_id"])
        self.assertEqual(response.json()["run_task_id"], "task-1")

    def test_create_issue_can_include_initial_plan_command(self) -> None:
        calls: list[tuple[str, int | None, str]] = []

        def fake_create_issue(token: str, full_name: str, title: str, body: str):
            calls.append(("issue", None, title))
            return {"id": 20, "number": 8, "title": title, "body": body, "state": "open"}

        def fake_comment(token: str, full_name: str, issue_number: int, body: str):
            calls.append(("comment", issue_number, body))
            return {"id": 21, "body": body, "html_url": "https://github.com/comment"}

        with (
            patch.object(workbench.github_client, "installation_token", return_value=SimpleNamespace(token="server-token")),
            patch.object(workbench.github_client, "create_issue", side_effect=fake_create_issue),
            patch.object(workbench.github_client, "create_issue_comment", side_effect=fake_comment),
            patch.object(workbench, "enqueue_agent_run", return_value="task-1"),
        ):
            response = self.client.post(
                f"/api/repositories/{self.repository.id}/issues",
                json={"title": "Improve mobile", "body": "Please tighten this.", "first_command": "plan"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(calls, [("issue", None, "Improve mobile"), ("comment", 8, "/plan add tests max 2 files")])
        self.assertTrue(response.json()["agent_run_id"])


if __name__ == "__main__":
    unittest.main()
