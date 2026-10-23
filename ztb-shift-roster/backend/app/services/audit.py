from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AuditLog


def record(session: Session, action: str, entity: str, entity_id: object = "", **detail: object) -> None:
    """Append an audit entry. Callers pass IDs and counts only, never names or free text."""
    session.add(AuditLog(action=action, entity=entity, entity_id=str(entity_id), detail=detail))
