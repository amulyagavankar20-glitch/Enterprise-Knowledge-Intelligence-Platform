"""Metadata-only audit helpers. Never pass question, answer, or document text."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import AuditLog

logger = logging.getLogger(__name__)


def record_audit(
    db: Session,
    *,
    actor_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Persist an audit event without logging or storing private content."""
    try:
        db.add(AuditLog(
            actor_id=actor_id,
            action=action[:100],
            resource_type=resource_type[:100],
            resource_id=resource_id[:100] if resource_id else None,
            details=details or {},
        ))
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(
            "audit_event_write_failed",
            extra={"error_type": type(exc).__name__, "action": action[:100]},
        )
