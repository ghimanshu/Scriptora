import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity


class OutboxEvent(Entity, Base):
    __tablename__ = "outbox_events"
    aggregate_id: Mapped[uuid.UUID]
    type: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB)
    dedupe_key: Mapped[str] = mapped_column(unique=True)
    state: Mapped[str] = mapped_column(default="PENDING", index=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None]


class Notification(Entity, Base):
    __tablename__ = "notifications"
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outbox_events.id"))
    type: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("recipient_id", "event_id"),)


class EmailDelivery(Entity, Base):
    __tablename__ = "email_deliveries"
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outbox_events.id"))
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    template_key: Mapped[str]
    state: Mapped[str] = mapped_column(default="PENDING")
    __table_args__ = (UniqueConstraint("event_id", "recipient_id", "template_key"),)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id: Mapped[str] = mapped_column(primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
