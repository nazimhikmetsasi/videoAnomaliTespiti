"""audit_log satiri yazan tek yardimci -- tum yazma uclari bunu cagirir
(ASAMA5_PLAN.md SS9.4/9.5). Commit cagirmaz: cagiran ucun kendi islemiyle
ayni transaction'da (tek db.commit()) atomik gitsin diye.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from api.db.models import AuditLog


def write_audit(
    db: Session, *, user_id: int, action: str, entity: str,
    entity_id: int | None = None, payload: dict[str, Any] | None = None,
) -> None:
    db.add(AuditLog(user_id=user_id, action=action, entity=entity,
                     entity_id=entity_id, payload=payload))
