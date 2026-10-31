from datetime import timedelta

from sqlalchemy import func, select
from test_workflow import setup_article

from app.db import session
from app.db.session import db_now
from app.models.notifications import EmailDelivery, Notification, OutboxEvent
from app.services.assignments import claim
from app.services.notifications import emit
from app.workers import expiry, outbox


def test_worker_restart_reconciles_overdue_reservations_once(pg, pg_engine, monkeypatch):
    article, reviewers = setup_article(pg)
    assignment = claim(pg, article.id, reviewers[0], article.lock_version)
    assignment.state = "RESERVED"
    assignment.assigned_at = db_now(pg) - timedelta(days=10)
    assignment.due_at = db_now(pg) - timedelta(days=5)
    article.status = "SUBMITTED"
    pg.commit()
    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    expiry.run()
    expiry.run()
    pg.refresh(assignment)
    assert assignment.state == "EXPIRED"
    assert (
        pg.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.dedupe_key == f"expired:{assignment.id}")
        )
        == 1
    )


def test_email_failure_preserves_deduplicated_in_app_notification(pg, pg_engine, monkeypatch):
    article, _ = setup_article(pg)
    emit(pg, article.id, "TEST_EVENT", [article.author_id], "test-notification")
    pg.commit()
    monkeypatch.setattr(session, "engine", lambda: pg_engine)

    def fail_send(*args):
        raise TimeoutError("test provider timeout")

    monkeypatch.setattr(outbox, "send_email", fail_send)
    outbox.run()
    pg.expire_all()
    event = pg.scalar(select(OutboxEvent))
    assert event.state == "PENDING"
    assert event.attempt_count == 1
    assert event.last_error == "TimeoutError"
    assert pg.scalar(select(func.count()).select_from(Notification)) == 1
    event.available_at = db_now(pg) - timedelta(seconds=1)
    pg.commit()
    sent = []
    monkeypatch.setattr(outbox, "send_email", lambda *args: sent.append(args))
    outbox.run()
    pg.refresh(event)
    assert event.state == "SENT"
    assert len(sent) == 1
    assert pg.scalar(select(func.count()).select_from(Notification)) == 1
    assert pg.scalar(select(EmailDelivery)).state == "SENT"
