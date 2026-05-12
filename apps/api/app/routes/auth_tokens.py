from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ApiRefreshToken, ApiTokenGrant
from app.services import api_tokens
from app.services.audit_log import list_audit_events, record_audit, serialize_audit_event
from app.services.auth import AuthenticatedUser, get_current_user
from app.services.rate_limits import check_rate_limit


router = APIRouter(prefix="/api/auth", tags=["auth-tokens"])


class TokenCreateRequest(BaseModel):
    label: str = Field(default="API token", min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: list(api_tokens.DEFAULT_API_SCOPES), max_length=16)
    refresh_expires_in_days: int = Field(default=30, ge=1, le=90)


class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenRevokeRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


def token_pair_response(pair: api_tokens.TokenPair) -> dict[str, object]:
    return {
        "token": api_tokens.serialize_grant(pair.grant),
        "token_type": "Bearer",
        "access_token": pair.access_token,
        "access_token_expires_at": pair.access_token_expires_at.isoformat(),
        "expires_in": max(1, int(api_tokens.settings.access_token_minutes)) * 60,
        "refresh_token": pair.refresh_token,
        "refresh_token_expires_at": pair.refresh_token_expires_at.isoformat(),
    }


def grant_for_refresh_token(session: Session, raw_refresh_token: str) -> ApiTokenGrant | None:
    token_hash = api_tokens.hash_refresh_token(raw_refresh_token.strip())
    refresh_model = session.scalar(
        select(ApiRefreshToken).where(ApiRefreshToken.token_hash == token_hash)
    )
    return refresh_model.grant if refresh_model else None


@router.get("/tokens")
def list_tokens(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    grants = session.scalars(
        select(ApiTokenGrant)
        .where(ApiTokenGrant.user_id == current_user.account.id)
        .order_by(desc(ApiTokenGrant.created_at))
    ).all()
    return {
        "available_scopes": list(api_tokens.ALL_API_SCOPES),
        "default_scopes": list(api_tokens.DEFAULT_API_SCOPES),
        "access_token_minutes": api_tokens.settings.access_token_minutes,
        "refresh_token_days": api_tokens.settings.refresh_token_days,
        "tokens": [api_tokens.serialize_grant(grant) for grant in grants],
    }


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
def create_token(
    body: TokenCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    check_rate_limit(f"token-create:{current_user.account.id}", limit=10)
    try:
        pair = api_tokens.create_token_pair(
            session,
            current_user.account,
            body.label,
            body.scopes,
            body.refresh_expires_in_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit(
        session,
        user_id=current_user.account.id,
        action="api_token.created",
        target_type="api_token_grant",
        target_id=str(pair.grant.id),
        payload={"label": pair.grant.label, "scopes": pair.grant.scopes_json},
    )
    session.commit()
    session.refresh(pair.grant)
    return token_pair_response(pair)


@router.post("/refresh")
def refresh_token(
    body: TokenRefreshRequest,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    check_rate_limit(f"token-refresh:{api_tokens.hash_refresh_token(body.refresh_token)[:20]}", limit=30)
    try:
        pair = api_tokens.rotate_refresh_token(session, body.refresh_token)
    except api_tokens.TokenRefreshError as exc:
        grant = grant_for_refresh_token(session, body.refresh_token)
        if grant is not None:
            record_audit(
                session,
                user_id=grant.user_id,
                action=f"api_token.{exc.code}",
                target_type="api_token_grant",
                target_id=str(grant.id),
                payload={"reason": exc.message},
            )
            session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message) from exc

    record_audit(
        session,
        user_id=pair.grant.user_id,
        action="api_token.refreshed",
        target_type="api_token_grant",
        target_id=str(pair.grant.id),
        payload={"scopes": pair.grant.scopes_json},
    )
    session.commit()
    session.refresh(pair.grant)
    return token_pair_response(pair)


@router.post("/revoke")
def revoke_token(
    body: TokenRevokeRequest,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    check_rate_limit(f"token-revoke:{api_tokens.hash_refresh_token(body.refresh_token)[:20]}", limit=30)
    grant = grant_for_refresh_token(session, body.refresh_token)
    if grant is not None and grant.status == "active":
        api_tokens.revoke_token_family(session, grant, "client_revoke")
        record_audit(
            session,
            user_id=grant.user_id,
            action="api_token.revoked",
            target_type="api_token_grant",
            target_id=str(grant.id),
            payload={"reason": "client_revoke"},
        )
        session.commit()
    return {"status": "revoked"}


@router.delete("/tokens/{token_id}")
def delete_token(
    token_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    grant = session.get(ApiTokenGrant, token_id)
    if grant is None or grant.user_id != current_user.account.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API token not found.")
    if grant.status == "active":
        api_tokens.revoke_token_family(session, grant, "user_deleted")
        record_audit(
            session,
            user_id=current_user.account.id,
            action="api_token.revoked",
            target_type="api_token_grant",
            target_id=str(grant.id),
            payload={"reason": "user_deleted"},
        )
        session.commit()
    return {"status": "revoked"}


@router.get("/audit")
def audit_events(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    events = list_audit_events(session, current_user.account.id)
    return {"events": [serialize_audit_event(event) for event in events]}
