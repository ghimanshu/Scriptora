from datetime import timedelta

from sqlalchemy import String, cast, exists, select

from app.core.config import get_settings
from app.db.session import db_now, session_factory
from app.models.notifications import OutboxEvent
from app.models.reviews import Assignment
from app.repositories.assignments import LIVE
from app.services.notifications import emit


def run():
    with session_factory().begin() as db:
        now = db_now(db)
        rows = db.scalars(
            select(Assignment)
            .where(
                Assignment.state.in_(LIVE),
                ~exists(
                    select(OutboxEvent.id).where(
                        OutboxEvent.type == "DEADLINE_REMINDER",
                        OutboxEvent.payload["assignment_id"].astext == cast(Assignment.id, String),
                    )
                ),
                Assignment.due_at > now,
                Assignment.due_at
                <= now + timedelta(hours=get_settings().reminder_before_deadline_hours),
            )
            .limit(100)
        ).all()
        for row in rows:
            emit(
                db,
                row.article_id,
                "DEADLINE_REMINDER",
                [row.reviewer_id],
                f"reminder:{row.id}:{row.due_at.isoformat()}",
                {"assignment_id": str(row.id)},
            )
