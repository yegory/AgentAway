from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import UserAccount
from app.services import api_tokens


@dataclass(frozen=True)
class AuthenticatedUser:
    account: UserAccount
    claims: dict[str, object]
    is_dev: bool = False
    auth_method: str = "clerk"
    scopes: frozenset[str] = field(default_factory=lambda: frozenset(api_tokens.ALL_API_SCOPES))
    token_grant_id: int | None = None
    token_family_id: str | None = None

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def clerk_is_configured() -> bool:
    return bool(settings.clerk_issuer or settings.clerk_jwks_url)


def auth_is_optional_for_dev() -> bool:
    return settings.app_env == "development" and not clerk_is_configured()


@lru_cache(maxsize=1)
def jwks_client() -> PyJWKClient:
    jwks_url = settings.clerk_jwks_url
    if not jwks_url and settings.clerk_issuer:
        jwks_url = settings.clerk_issuer.rstrip("/") + "/.well-known/jwks.json"
    if not jwks_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk JWT verification is not configured.",
        )
    return PyJWKClient(jwks_url)


def upsert_user_account(
    session: Session,
    clerk_user_id: str,
    email: str = "",
    display_name: str = "",
) -> UserAccount:
    account = session.scalar(select(UserAccount).where(UserAccount.clerk_user_id == clerk_user_id))
    if account is None:
        account = UserAccount(clerk_user_id=clerk_user_id)
        session.add(account)

    if email:
        account.email = email
    if display_name:
        account.display_name = display_name

    session.commit()
    session.refresh(account)
    return account


def decode_clerk_token(token: str) -> dict[str, object]:
    try:
        signing_key = jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer or None,
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token.") from exc

    authorized_parties = [
        party.strip()
        for party in settings.clerk_authorized_parties.split(",")
        if party.strip()
    ]
    if authorized_parties:
        azp = str(claims.get("azp") or "")
        if azp not in authorized_parties:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth party.")

    return claims


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: Session = Depends(get_session),
) -> AuthenticatedUser:
    if auth_is_optional_for_dev():
        account = upsert_user_account(
            session,
            clerk_user_id=settings.agentaway_dev_user_id,
            email="dev@agentaway.local",
            display_name="Local Dev",
        )
        return AuthenticatedUser(
            account=account,
            claims={"sub": settings.agentaway_dev_user_id},
            is_dev=True,
            auth_method="dev",
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth token.")

    token = authorization.split(" ", 1)[1].strip()
    if is_agentaway_access_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="AgentAway API tokens are accepted on /api/v1 routes.",
        )

    claims = decode_clerk_token(token)
    clerk_user_id = str(claims.get("sub") or "")
    if not clerk_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth subject.")

    email = str(claims.get("email") or claims.get("primary_email_address") or "")
    display_name = str(claims.get("name") or claims.get("full_name") or claims.get("username") or "")
    account = upsert_user_account(session, clerk_user_id=clerk_user_id, email=email, display_name=display_name)
    return AuthenticatedUser(account=account, claims=claims)


def is_agentaway_access_token(token: str) -> bool:
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return False
    return claims.get("iss") == api_tokens.ACCESS_TOKEN_ISSUER and claims.get("typ") == "access"


def get_current_user_or_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: Session = Depends(get_session),
) -> AuthenticatedUser:
    if auth_is_optional_for_dev() and not authorization:
        account = upsert_user_account(
            session,
            clerk_user_id=settings.agentaway_dev_user_id,
            email="dev@agentaway.local",
            display_name="Local Dev",
        )
        return AuthenticatedUser(
            account=account,
            claims={"sub": settings.agentaway_dev_user_id},
            is_dev=True,
            auth_method="dev",
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth token.")

    token = authorization.split(" ", 1)[1].strip()
    if is_agentaway_access_token(token):
        account, grant, claims, scopes = api_tokens.verify_access_token(session, token)
        return AuthenticatedUser(
            account=account,
            claims=claims,
            auth_method="api_token",
            scopes=frozenset(scopes),
            token_grant_id=grant.id,
            token_family_id=grant.token_family_id,
        )

    claims = decode_clerk_token(token)
    clerk_user_id = str(claims.get("sub") or "")
    if not clerk_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth subject.")
    email = str(claims.get("email") or claims.get("primary_email_address") or "")
    display_name = str(claims.get("name") or claims.get("full_name") or claims.get("username") or "")
    account = upsert_user_account(session, clerk_user_id=clerk_user_id, email=email, display_name=display_name)
    return AuthenticatedUser(account=account, claims=claims)


def require_scopes(*required_scopes: str):
    def dependency(current_user: AuthenticatedUser = Depends(get_current_user_or_token)) -> AuthenticatedUser:
        missing = [scope for scope in required_scopes if scope not in current_user.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {', '.join(missing)}",
            )
        return current_user

    return dependency
