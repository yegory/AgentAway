from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet
from fastapi import HTTPException, status

from app.config import settings


def encryption_key() -> bytes:
    configured = settings.app_encryption_key.strip()
    if configured:
        return configured.encode("utf-8")

    if settings.app_env == "development":
        digest = hashlib.sha256(b"agentaway-local-development-key").digest()
        return base64.urlsafe_b64encode(digest)

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="APP_ENCRYPTION_KEY is required in production.",
    )


def fernet() -> Fernet:
    return Fernet(encryption_key())


def encrypt_secret(value: str) -> str:
    return fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def key_hint(value: str) -> str:
    clean = value.strip()
    if len(clean) <= 4:
        return "****"
    return f"****{clean[-4:]}"
