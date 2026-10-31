from datetime import timedelta

from sqlalchemy import and_, or_, select

from app.db.session import db_now
from app.models.notifications import OutboxEvent


def claim_event(db):
    now = db_now(db)
    event = db.scalar(
        select(OutboxEvent)
        .where(
            or_(
                and_(OutboxEvent.state == "PENDING", OutboxEvent.available_at <= now),
                and_(OutboxEvent.state == "PROCESSING", OutboxEvent.lease_until <= now),
            )
        )
        .order_by(OutboxEvent.available_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if event:
        event.state = "PROCESSING"
        event.lease_until = now + timedelta(minutes=5)
        event.attempt_count += 1
    return event
