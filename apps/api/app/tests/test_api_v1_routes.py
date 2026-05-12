import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.models import Base, GitHubInstallation, Repository, RepositoryAccess, UserAccount
from app.routes import api_v1
from app.services import api_tokens


class ApiV1RouteTests(unittest.TestCase):
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
        self.other_account = UserAccount(clerk_user_id="user_2", email="other@example.com")
        self.other_repo = Repository(
            github_repo_id=100,
            owner="other",
            name="secret",
            full_name="other/secret",
        )
        self.session.add_all([self.account, self.installation, self.repository, self.other_account, self.other_repo])
        self.session.flush()
        self.session.add(
            RepositoryAccess(
                user_id=self.account.id,
                repository_id=self.repository.id,
                role="admin",
            )
        )
        self.session.add(
            RepositoryAccess(
                user_id=self.other_account.id,
                repository_id=self.other_repo.id,
                role="admin",
            )
        )
        self.session.commit()

        app = FastAPI()
        app.include_router(api_v1.router)

        def override_session():
            yield self.session

        app.dependency_overrides[get_session] = override_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def bearer(self, scopes: list[str]) -> dict[str, str]:
        pair = api_tokens.create_token_pair(self.session, self.account, "test", scopes)
        self.session.commit()
        return {"Authorization": f"Bearer {pair.access_token}"}

    def test_me_returns_scoped_principal(self) -> None:
        response = self.client.get("/api/v1/me", headers=self.bearer(["account:read"]))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user"]["email"], "dev@example.com")
        self.assertEqual(body["auth"]["method"], "api_token")
        self.assertEqual(body["auth"]["scopes"], ["account:read"])

    def test_list_repositories_requires_scope(self) -> None:
        response = self.client.get("/api/v1/repositories", headers=self.bearer(["account:read"]))

        self.assertEqual(response.status_code, 403)

    def test_list_repositories_returns_only_accessible_repos(self) -> None:
        with patch.object(api_v1.workbench.github_client, "github_app_configured", return_value=False):
            response = self.client.get("/api/v1/repositories", headers=self.bearer(["repos:read"]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([repo["full_name"] for repo in response.json()["repositories"]], ["agentaway/demo"])

    def test_issue_list_checks_repo_access_before_github_call(self) -> None:
        with patch.object(api_v1.workbench.github_client, "installation_token") as token_mock:
            response = self.client.get(
                f"/api/v1/repositories/{self.other_repo.id}/issues",
                headers=self.bearer(["issues:read"]),
            )

        self.assertEqual(response.status_code, 404)
        token_mock.assert_not_called()

    def test_command_route_requires_command_scope(self) -> None:
        with patch.object(api_v1.workbench.github_client, "create_issue_comment") as comment_mock:
            response = self.client.post(
                f"/api/v1/repositories/{self.repository.id}/issues/7/commands",
                headers=self.bearer(["issues:write"]),
                json={"command": "plan"},
            )

        self.assertEqual(response.status_code, 403)
        comment_mock.assert_not_called()

    def test_command_route_posts_valid_command(self) -> None:
        posted: dict[str, object] = {}

        def fake_comment(token: str, full_name: str, issue_number: int, body: str):
            posted["token"] = token
            posted["full_name"] = full_name
            posted["issue_number"] = issue_number
            posted["body"] = body
            return {"id": 10, "body": body, "html_url": "https://github.com/comment"}

        with (
            patch.object(api_v1.workbench.github_client, "installation_token", return_value=SimpleNamespace(token="server-token")),
            patch.object(api_v1.workbench.github_client, "create_issue_comment", side_effect=fake_comment),
        ):
            response = self.client.post(
                f"/api/v1/repositories/{self.repository.id}/issues/7/commands",
                headers=self.bearer(["commands:write"]),
                json={"command": "plan", "constraints": ["add tests"]},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(posted["body"], "/plan add tests")
        self.assertEqual(response.json()["command"]["command"], "plan")


if __name__ == "__main__":
    unittest.main()
