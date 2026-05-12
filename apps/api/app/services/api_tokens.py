from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ApiRefreshToken, ApiTokenGrant, UserAccount


ALL_API_SCOPES = (
    "account:read",
    "repos:read",
    "issues:read",
    "issues:write",
    "commands:write",
    "runs:read",
    "runs:write",
)
DEFAULT_API_SCOPES = ("account:read", "repos:read", "issues:read", "runs:read")
ACCESS_TOKEN_ISSUER = "agentaway"
ACCESS_TOKEN_AUDIENCE = "agentaway-api"


class TokenRefreshError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TokenPair:
    grant: ApiTokenGrant
    access_token: str
    access_token_expires_at: datetime
    refresh_token: str
    refresh_token_expires_at: datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def access_token_secret() -> str:
    configured = settings.app_access_token_secret.strip()
    if configured:
        return configured
    if settings.app_env == "development":
        return hashlib.sha256(b"agentaway-local-access-token-secret").hexdigest()
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="APP_ACCESS_TOKEN_SECRET is required in production.",
    )


def normalize_scopes(scopes: list[str] | tuple[str, ...] | None) -> list[str]:
    values = list(scopes or DEFAULT_API_SCOPES)
    normalized: list[str] = []
    allowed = set(ALL_API_SCOPES)
    for scope in values:
        clean = str(scope).strip().lower()
        if not clean:
            continue
        if clean not in allowed:
            raise ValueError(f"Unsupported API token scope: {clean}")
        if clean not in normalized:
            normalized.append(clean)
    return normalized or list(DEFAULT_API_SCOPES)


def generate_token_family_id() -> str:
    return "awtf_" + secrets.token_urlsafe(24)


def generate_refresh_token() -> str:
    return "awrt_" + secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hmac.new(
        access_token_secret().encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def access_token_expiry(now: datetime | None = None) -> datetime:
    base = now or utc_now()
    minutes = max(1, int(settings.access_token_minutes))
    return base + timedelta(minutes=minutes)


def refresh_token_expiry(days: int | None = None, now: datetime | None = None) -> datetime:
    base = now or utc_now()
    return base + timedelta(days=max(1, int(days or settings.refresh_token_days)))


def issue_access_token(grant: ApiTokenGrant, now: datetime | None = None) -> tuple[str, datetime]:
    issued_at = now or utc_now()
    expires_at = access_token_expiry(issued_at)
    payload: dict[str, Any] = {
        "iss": ACCESS_TOKEN_ISSUER,
        "aud": ACCESS_TOKEN_AUDIENCE,
        "typ": "access",
        "sub": grant.user.clerk_user_id,
        "account_id": grant.user_id,
        "jti": "awtj_" + secrets.token_urlsafe(18),
        "scopes": normalize_scopes(list(grant.scopes_json or [])),
        "token_family_id": grant.token_family_id,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, access_token_secret(), algorithm="HS256"), expires_at


def create_token_pair(
    session: Session,
    user: UserAccount,
    label: str,
    scopes: list[str] | None = None,
    refresh_days: int | None = None,
) -> TokenPair:
    clean_scopes = normalize_scopes(scopes)
    refresh_token = generate_refresh_token()
    expires_at = refresh_token_expiry(refresh_days)
    grant = ApiTokenGrant(
        user=user,
        token_family_id=generate_token_family_id(),
        label=label.strip() or "API token",
        scopes_json=clean_scopes,
        expires_at=expires_at,
    )
    session.add(grant)
    session.flush()
    refresh_model = ApiRefreshToken(
        grant=grant,
        token_hash=hash_refresh_token(refresh_token),
        expires_at=expires_at,
    )
    session.add(refresh_model)
    access_token, access_expires_at = issue_access_token(grant)
    return TokenPair(
        grant=grant,
        access_token=access_token,
        access_token_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_token_expires_at=expires_at,
    )


def revoke_token_family(
    session: Session,
    grant: ApiTokenGrant,
    reason: str,
    now: datetime | None = None,
) -> None:
    revoked_at = now or utc_now()
    grant.status = "revoked"
    grant.revoked_at = revoked_at
    grant.revoked_reason = reason
    tokens = session.scalars(select(ApiRefreshToken).where(ApiRefreshToken.grant_id == grant.id)).all()
    for token in tokens:
        if token.revoked_at is None:
            token.revoked_at = revoked_at


def rotate_refresh_token(session: Session, raw_refresh_token: str) -> TokenPair:
    now = utc_now()
    token_hash = hash_refresh_token(raw_refresh_token.strip())
    refresh_model = session.scalar(
        select(ApiRefreshToken).where(ApiRefreshToken.token_hash == token_hash)
    )
    if refresh_model is None:
        raise TokenRefreshError("invalid_refresh_token", "Refresh token is invalid.")

    grant = refresh_model.grant
    if grant.status != "active" or grant.revoked_at is not None:
        raise TokenRefreshError("revoked_token_family", "Token family is revoked.")

    if refresh_model.used_at is not None or refresh_model.revoked_at is not None:
        revoke_token_family(session, grant, "refresh_reuse_detected", now)
        raise TokenRefreshError("refresh_reuse_detected", "Refresh token reuse was detected.")

    grant_expires_at = as_utc(grant.expires_at)
    refresh_expires_at = as_utc(refresh_model.expires_at)
    if (grant_expires_at and grant_expires_at <= now) or (refresh_expires_at and refresh_expires_at <= now):
        revoke_token_family(session, grant, "refresh_expired", now)
        raise TokenRefreshError("refresh_token_expired", "Refresh token expired.")

    new_refresh_token = generate_refresh_token()
    new_refresh_model = ApiRefreshToken(
        grant=grant,
        token_hash=hash_refresh_token(new_refresh_token),
        expires_at=grant.expires_at or refresh_token_expiry(),
    )
    session.add(new_refresh_model)
    session.flush()
    refresh_model.used_at = now
    refresh_model.replaced_by_id = new_refresh_model.id
    grant.last_used_at = now
    access_token, access_expires_at = issue_access_token(grant, now)
    return TokenPair(
        grant=grant,
        access_token=access_token,
        access_token_expires_at=access_expires_at,
        refresh_token=new_refresh_token,
        refresh_token_expires_at=as_utc(new_refresh_model.expires_at) or refresh_token_expiry(),
    )


def verify_access_token(session: Session, token: str) -> tuple[UserAccount, ApiTokenGrant, dict[str, Any], set[str]]:
    try:
        claims = jwt.decode(
            token,
            access_token_secret(),
            algorithms=["HS256"],
            audience=ACCESS_TOKEN_AUDIENCE,
            issuer=ACCESS_TOKEN_ISSUER,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.") from exc

    if claims.get("typ") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token type.")

    token_family_id = str(claims.get("token_family_id") or "")
    account_id = int(claims.get("account_id") or 0)
    grant = session.scalar(
        select(ApiTokenGrant).where(ApiTokenGrant.token_family_id == token_family_id)
    )
    if grant is None or grant.user_id != account_id or grant.status != "active" or grant.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token is revoked.")

    grant_expires_at = as_utc(grant.expires_at)
    if grant_expires_at and grant_expires_at <= utc_now():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token grant expired.")

    grant.last_used_at = utc_now()
    session.commit()
    scope_set = set(normalize_scopes(list(grant.scopes_json or [])))
    return grant.user, grant, claims, scope_set


def serialize_grant(grant: ApiTokenGrant) -> dict[str, Any]:
    return {
        "id": grant.id,
        "label": grant.label,
        "token_family_id": grant.token_family_id,
        "scopes": normalize_scopes(list(grant.scopes_json or [])),
        "status": grant.status,
        "expires_at": as_utc(grant.expires_at).isoformat() if as_utc(grant.expires_at) else None,
        "last_used_at": as_utc(grant.last_used_at).isoformat() if as_utc(grant.last_used_at) else None,
        "revoked_at": as_utc(grant.revoked_at).isoformat() if as_utc(grant.revoked_at) else None,
        "revoked_reason": grant.revoked_reason,
        "created_at": as_utc(grant.created_at).isoformat() if as_utc(grant.created_at) else None,
        "updated_at": as_utc(grant.updated_at).isoformat() if as_utc(grant.updated_at) else None,
    }
