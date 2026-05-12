from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from services import settings


def encryption_key() -> bytes:
    configured = settings.APP_ENCRYPTION_KEY.strip()
    if configured:
        return configured.encode("utf-8")
    if settings.APP_ENV == "development":
        digest = hashlib.sha256(b"agentaway-local-development-key").digest()
        return base64.urlsafe_b64encode(digest)
    raise RuntimeError("APP_ENCRYPTION_KEY is required in production.")


def decrypt_secret(value: str) -> str:
    return Fernet(encryption_key()).decrypt(value.encode("utf-8")).decode("utf-8")
