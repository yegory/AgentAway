import unittest
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings, validate_production_settings
from app.db import get_session
from app.models import ApiRefreshToken, Base, UserAccount
from app.routes import auth_tokens
from app.services import api_tokens
from app.services.audit_log import list_audit_events, record_audit
from app.services.auth import AuthenticatedUser


class ApiTokenServiceTests(unittest.TestCase):
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
        self.session.add(self.account)
        self.session.commit()
        app = FastAPI()
        app.include_router(auth_tokens.router)

        def override_session():
            yield self.session

        def override_user():
            return AuthenticatedUser(account=self.account, claims={"sub": "user_1"}, is_dev=True)

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[auth_tokens.get_current_user] = override_user
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_access_token_verifies_active_grant(self) -> None:
        pair = api_tokens.create_token_pair(
            self.session,
            self.account,
            "CLI",
            ["account:read", "runs:read"],
        )
        self.session.commit()

        account, grant, claims, scopes = api_tokens.verify_access_token(self.session, pair.access_token)

        self.assertEqual(account.id, self.account.id)
        self.assertEqual(grant.id, pair.grant.id)
        self.assertEqual(claims["token_family_id"], pair.grant.token_family_id)
        self.assertEqual(scopes, {"account:read", "runs:read"})

    def test_refresh_rotation_revokes_family_on_reuse(self) -> None:
        pair = api_tokens.create_token_pair(self.session, self.account, "CLI", ["runs:read"])
        self.session.commit()

        rotated = api_tokens.rotate_refresh_token(self.session, pair.refresh_token)
        self.session.commit()

        self.assertNotEqual(pair.refresh_token, rotated.refresh_token)
        old_refresh = self.session.scalar(
            select(ApiRefreshToken).where(ApiRefreshToken.token_hash == api_tokens.hash_refresh_token(pair.refresh_token))
        )
        self.assertIsNotNone(old_refresh)
        assert old_refresh is not None
        self.assertIsNotNone(old_refresh.used_at)

        with self.assertRaises(api_tokens.TokenRefreshError):
            api_tokens.rotate_refresh_token(self.session, pair.refresh_token)
        self.session.commit()
        self.session.refresh(pair.grant)

        self.assertEqual(pair.grant.status, "revoked")
        self.assertEqual(pair.grant.revoked_reason, "refresh_reuse_detected")

    def test_expired_access_token_is_rejected(self) -> None:
        pair = api_tokens.create_token_pair(self.session, self.account, "CLI", ["runs:read"])
        self.session.commit()
        now = datetime.now(UTC)
        expired = jwt.encode(
            {
                "iss": api_tokens.ACCESS_TOKEN_ISSUER,
                "aud": api_tokens.ACCESS_TOKEN_AUDIENCE,
                "typ": "access",
                "sub": self.account.clerk_user_id,
                "account_id": self.account.id,
                "jti": "expired",
                "scopes": ["runs:read"],
                "token_family_id": pair.grant.token_family_id,
                "iat": int((now - timedelta(minutes=30)).timestamp()),
                "exp": int((now - timedelta(minutes=1)).timestamp()),
            },
            api_tokens.access_token_secret(),
            algorithm="HS256",
        )

        with self.assertRaises(HTTPException) as raised:
            api_tokens.verify_access_token(self.session, expired)

        self.assertEqual(raised.exception.status_code, 401)

    def test_scope_helper_rejects_missing_scope(self) -> None:
        principal = AuthenticatedUser(
            account=self.account,
            claims={"sub": "user_1"},
            auth_method="api_token",
            scopes=frozenset({"runs:read"}),
        )

        self.assertTrue(principal.has_scope("runs:read"))
        self.assertFalse(principal.has_scope("runs:write"))

    def test_audit_log_records_events(self) -> None:
        record_audit(
            self.session,
            user_id=self.account.id,
            action="api_token.created",
            target_type="api_token_grant",
            target_id="1",
            payload={"scopes": ["runs:read"]},
        )
        self.session.commit()

        events = list_audit_events(self.session, self.account.id)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, "api_token.created")

    def test_token_routes_create_refresh_and_revoke(self) -> None:
        create_response = self.client.post(
            "/api/auth/tokens",
            json={"label": "CLI", "scopes": ["account:read", "runs:read"], "refresh_expires_in_days": 7},
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertTrue(created["access_token"])
        self.assertTrue(created["refresh_token"])

        list_response = self.client.get("/api/auth/tokens")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["tokens"][0]["label"], "CLI")

        refresh_response = self.client.post(
            "/api/auth/refresh",
            json={"refresh_token": created["refresh_token"]},
        )
        self.assertEqual(refresh_response.status_code, 200)
        refreshed = refresh_response.json()
        self.assertNotEqual(refreshed["refresh_token"], created["refresh_token"])

        revoke_response = self.client.post(
            "/api/auth/revoke",
            json={"refresh_token": refreshed["refresh_token"]},
        )
        self.assertEqual(revoke_response.status_code, 200)

    def test_production_requires_security_secrets(self) -> None:
        old_env = settings.app_env
        old_encryption = settings.app_encryption_key
        old_access = settings.app_access_token_secret
        old_webhook = settings.github_webhook_secret
        old_issuer = settings.clerk_issuer
        old_jwks = settings.clerk_jwks_url
        settings.app_env = "production"
        settings.app_encryption_key = ""
        settings.app_access_token_secret = ""
        settings.github_webhook_secret = ""
        settings.clerk_issuer = ""
        settings.clerk_jwks_url = ""
        try:
            with self.assertRaises(RuntimeError):
                validate_production_settings()
        finally:
            settings.app_env = old_env
            settings.app_encryption_key = old_encryption
            settings.app_access_token_secret = old_access
            settings.github_webhook_secret = old_webhook
            settings.clerk_issuer = old_issuer
            settings.clerk_jwks_url = old_jwks


if __name__ == "__main__":
    unittest.main()
