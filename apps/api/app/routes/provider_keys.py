from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ProviderCredential
from app.services.audit_log import record_audit
from app.services.auth import AuthenticatedUser, get_current_user
from app.services.crypto import decrypt_secret, encrypt_secret, key_hint
from app.services.providers import normalize_provider, provider_defaults, test_provider_key


router = APIRouter(prefix="/api/provider-keys", tags=["provider-keys"])


class ProviderKeyCreate(BaseModel):
    provider: str
    api_key: str = Field(min_length=1)
    model_name: str | None = None
    base_url: str | None = None
    make_default: bool = True


def serialize_credential(credential: ProviderCredential) -> dict[str, object]:
    return {
        "id": credential.id,
        "provider": credential.provider,
        "key_hint": credential.key_hint,
        "model_name": credential.model_name,
        "base_url": credential.base_url,
        "status": credential.status,
        "last_tested_at": credential.last_tested_at.isoformat() if credential.last_tested_at else None,
        "created_at": credential.created_at.isoformat(),
        "updated_at": credential.updated_at.isoformat(),
    }


@router.get("")
def list_provider_keys(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    credentials = session.scalars(
        select(ProviderCredential)
        .where(ProviderCredential.user_id == current_user.account.id)
        .order_by(desc(ProviderCredential.updated_at))
    ).all()
    return {
        "default_provider": current_user.account.default_provider,
        "provider_keys": [serialize_credential(credential) for credential in credentials],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def upsert_provider_key(
    body: ProviderKeyCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        provider = normalize_provider(body.provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    defaults = provider_defaults(provider)
    credential = session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.user_id == current_user.account.id,
            ProviderCredential.provider == provider,
        )
    )
    if credential is None:
        credential = ProviderCredential(user_id=current_user.account.id, provider=provider, encrypted_api_key="")
        session.add(credential)

    api_key = body.api_key.strip()
    credential.encrypted_api_key = encrypt_secret(api_key)
    credential.key_hint = key_hint(api_key)
    credential.model_name = (body.model_name or defaults.model_name).strip()
    credential.base_url = (body.base_url or defaults.base_url).strip().rstrip("/")
    credential.status = "stored"

    if body.make_default or not current_user.account.default_provider:
        current_user.account.default_provider = provider

    record_audit(
        session,
        user_id=current_user.account.id,
        action="provider_key.saved",
        target_type="provider",
        target_id=provider,
        payload={"model_name": credential.model_name, "base_url": credential.base_url},
    )
    session.commit()
    session.refresh(credential)
    return {"provider_key": serialize_credential(credential)}


@router.delete("/{provider}")
def delete_provider_key(
    provider: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    try:
        provider = normalize_provider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    credential = session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.user_id == current_user.account.id,
            ProviderCredential.provider == provider,
        )
    )
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider key not found.")

    session.delete(credential)
    if current_user.account.default_provider == provider:
        current_user.account.default_provider = None
    record_audit(
        session,
        user_id=current_user.account.id,
        action="provider_key.deleted",
        target_type="provider",
        target_id=provider,
        payload={},
    )
    session.commit()
    return {"status": "deleted"}


@router.post("/{provider}/test")
async def test_key(
    provider: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        provider = normalize_provider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    credential = session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.user_id == current_user.account.id,
            ProviderCredential.provider == provider,
        )
    )
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider key not found.")

    result = await test_provider_key(provider, decrypt_secret(credential.encrypted_api_key), credential.base_url)
    credential.status = result["status"]
    credential.last_tested_at = datetime.now(UTC)
    record_audit(
        session,
        user_id=current_user.account.id,
        action="provider_key.tested",
        target_type="provider",
        target_id=provider,
        payload={"status": result["status"]},
    )
    session.commit()
    return result
