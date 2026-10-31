import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import db_now
from app.models.audit import AuditEvent
from app.models.notifications import OutboxEvent
from app.models.users import UserRole


def admins(db):
    return list(db.scalars(select(UserRole.user_id).where(UserRole.role == "ADMIN")))


def emit(db, aggregate, kind, recipients, key, extra=None):
    payload = {"recipients": [str(x) for x in set(recipients)], "entity_id": str(aggregate)}
    payload.update(extra or {})
    db.execute(
        insert(OutboxEvent)
        .values(
            id=uuid.uuid4(),
            aggregate_id=aggregate,
            type=kind,
            payload=payload,
            dedupe_key=key,
            state="PENDING",
            attempt_count=0,
            available_at=db_now(db),
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )


def audit(db, actor, action, entity, data=None):
    db.add(
        AuditEvent(
            actor_id=actor.id if actor else None,
            action=action,
            entity_type=entity.__tablename__,
            entity_id=entity.id,
            data=data or {},
            request_id=db.info.get("request_id"),
        )
    )
