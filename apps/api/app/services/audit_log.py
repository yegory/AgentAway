from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.services.api_tokens import as_utc


def record_audit(
    session: Session,
    *,
    user_id: int | None,
    action: str,
    target_type: str = "",
    target_id: str = "",
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id or ""),
        payload_json=payload or {},
    )
    session.add(entry)
    return entry


def list_audit_events(session: Session, user_id: int, limit: int = 50) -> list[AuditLog]:
    return session.scalars(
        select(AuditLog)
        .where(AuditLog.user_id == user_id)
        .order_by(desc(AuditLog.created_at))
        .limit(max(1, min(limit, 100)))
    ).all()


def serialize_audit_event(entry: AuditLog) -> dict[str, Any]:
    return {
        "id": entry.id,
        "action": entry.action,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "payload_json": entry.payload_json,
        "created_at": as_utc(entry.created_at).isoformat() if as_utc(entry.created_at) else None,
    }
