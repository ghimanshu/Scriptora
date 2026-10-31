import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity


class AuditEvent(Entity, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str]
    entity_type: Mapped[str]
    entity_id: Mapped[uuid.UUID]
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    request_id: Mapped[str | None]


class IdempotencyKey(Entity, Base):
    __tablename__ = "idempotency_keys"
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    route: Mapped[str]
    key: Mapped[str]
    request_hash: Mapped[str]
    response_code: Mapped[int]
    response_body: Mapped[dict] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("actor_id", "route", "key"),)
