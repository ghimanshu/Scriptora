import uuid

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text
from test_workflow import setup_article

from app.core.security import issue_session
from app.db import session
from app.db.session import db_now
from app.main import app
from app.models.notifications import Notification, OutboxEvent
from app.models.users import User, UserRole
from app.services.notifications import emit
from app.workers import outbox


def setup_users(pg, pg_engine, monkeypatch):
    article, reviewers = setup_article(pg)
    author = pg.get(User, article.author_id)
    pg.add(UserRole(user_id=author.id, role="AUTHOR"))
    own = {"Authorization": "Bearer " + issue_session(pg, author)["access_token"]}
    other = {"Authorization": "Bearer " + issue_session(pg, reviewers[0])["access_token"]}
    pg.commit()
    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    return article, author, reviewers[0], own, other


def mutation(headers):
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def test_notification_is_immediate_deduplicated_and_survives_email_failure(
    pg, pg_engine, monkeypatch
):
    article, author, reviewer, own, other = setup_users(pg, pg_engine, monkeypatch)
    emit(
        pg,
        article.id,
        "TEST_EVENT",
        [author.id, author.id],
        "immediate-notification",
        {"title": "Article update"},
    )
    pg.commit()
    notice = pg.scalar(select(Notification))
    assert notice.recipient_id == author.id
    assert notice.read_at is None
    assert pg.scalar(select(OutboxEvent)).state == "PENDING"
    # Reading does not wait for the email worker and must not be reset by its retry.
    with TestClient(app) as client:
        response = client.get("/api/v1/notifications/summary", headers=own)
        assert response.status_code == 200, response.text
        assert response.json()["unread_count"] == 1
        assert (
            client.post(
                f"/api/v1/notifications/{notice.id}/read", headers=mutation(own), json={}
            ).status_code
            == 200
        )
    emit(pg, article.id, "TEST_EVENT", [author.id], "immediate-notification")
    pg.commit()

    def fail_send(*args):
        raise TimeoutError("Mock SMTP unavailable")

    monkeypatch.setattr(outbox, "send_email", fail_send)
    outbox.run()
    pg.expire_all()
    assert pg.scalar(select(func.count()).select_from(Notification)) == 1
    assert pg.get(Notification, notice.id).read_at is not None
    assert pg.scalar(select(OutboxEvent)).state == "PENDING"


def test_notifications_have_private_counts_filters_pagination_and_read_controls(
    pg, pg_engine, monkeypatch
):
    article, author, reviewer, own, other = setup_users(pg, pg_engine, monkeypatch)
    for number in range(3):
        emit(
            pg,
            article.id,
            "ASSIGNED",
            [author.id],
            f"own:{number}",
            {"encrypted_token": "private-secret", "title": f"Update {number}"},
        )
        pg.commit()
    emit(pg, article.id, "TEST_EVENT", [reviewer.id], "other-user")
    pg.commit()
    with TestClient(app) as client:
        assert client.get("/api/v1/notifications").status_code == 401
        result = client.get("/api/v1/notifications?limit=1", headers=own)
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["total_count"] == data["unread_count"] == 3
        assert data["items"][0]["title"] == "Update 2"
        assert "private-secret" not in result.text and "encrypted_token" not in result.text
        assert data["items"][0]["href"] == f"/author/articles/{article.id}"
        first = data["items"][0]["id"]
        next_page = client.get(
            "/api/v1/notifications", params={"limit": 1, "cursor": data["next_cursor"]}, headers=own
        ).json()
        assert next_page["items"][0]["id"] != first
        assert (
            client.post(
                f"/api/v1/notifications/{first}/read", headers=mutation(other), json={}
            ).status_code
            == 404
        )
        read = client.post(
            f"/api/v1/notifications/{first}/read", headers=mutation(own), json={}
        ).json()
        assert read["is_read"] is True
        again = client.post(
            f"/api/v1/notifications/{first}/read", headers=mutation(own), json={}
        ).json()
        assert again["read_at"] == read["read_at"]
        assert (
            len(client.get("/api/v1/notifications?status=read", headers=own).json()["items"]) == 1
        )
        assert (
            len(client.get("/api/v1/notifications?status=unread", headers=own).json()["items"]) == 2
        )
        assert client.get("/api/v1/notifications?cursor=invalid", headers=own).status_code == 422
        cleared = client.post(
            "/api/v1/notifications/read-all", headers=mutation(own), json={}
        ).json()
        assert cleared == {"updated_count": 2, "unread_count": 0}
        assert (
            client.get("/api/v1/notifications/summary", headers=other).json()["unread_count"] == 1
        )
        unread = client.post(
            f"/api/v1/notifications/{first}/unread", headers=mutation(own), json={}
        ).json()
        assert unread["read_at"] is None and unread["is_read"] is False
        assert client.get("/api/v1/notifications/summary", headers=own).json()["unread_count"] == 1


def test_failed_business_transaction_rolls_back_notification_and_email_event(
    pg, pg_engine, monkeypatch
):
    article, author, reviewer, own, other = setup_users(pg, pg_engine, monkeypatch)
    emit(pg, article.id, "TEST_EVENT", [author.id], "rolled-back")
    assert pg.scalar(select(func.count()).select_from(Notification)) == 1
    pg.rollback()
    assert pg.scalar(select(func.count()).select_from(Notification)) == 0
    assert pg.scalar(select(func.count()).select_from(OutboxEvent)) == 0


def test_migration_backfills_missing_notifications_without_resetting_read_state(
    pg, pg_engine, monkeypatch
):
    article, author, reviewer, own, other = setup_users(pg, pg_engine, monkeypatch)
    emit(pg, article.id, "TEST_EVENT", [author.id], "kept-read")
    emit(
        pg,
        article.id,
        "TEST_EVENT",
        [author.id],
        "missing-copy",
        {"encrypted_token": "hidden-token"},
    )
    pg.commit()
    first = pg.scalar(
        select(Notification).join(OutboxEvent).where(OutboxEvent.dedupe_key == "kept-read")
    )
    first.read_at = db_now(pg)
    first_id, read_at = first.id, first.read_at
    missing_event = pg.scalar(select(OutboxEvent).where(OutboxEvent.dedupe_key == "missing-copy"))
    missing_id = missing_event.id
    pg.execute(delete(Notification).where(Notification.event_id == missing_id))
    pg.commit()
    pg.close()
    config = Config("alembic.ini")
    command.downgrade(config, "0009_draft_subjects")
    try:
        command.upgrade(config, "head")
        assert pg.get(Notification, first_id).read_at == read_at
        restored = pg.scalar(select(Notification).where(Notification.event_id == missing_id))
        assert restored is not None and restored.read_at is None
        assert "encrypted_token" not in restored.payload
        assert pg.scalar(select(func.count()).select_from(Notification)) == 2
        indexes = set(
            pg.scalars(text("SELECT indexname FROM pg_indexes WHERE tablename='notifications'"))
        )
        assert {
            "ix_notifications_recipient_created",
            "ix_notifications_recipient_unread",
        } <= indexes
    finally:
        pg.close()
        command.upgrade(config, "head")


def test_article_review_and_payment_statuses_create_notifications_for_intended_users(pg):
    from datetime import timedelta

    from test_payments import approved

    from app.schemas.payments import PaymentInput, Publish, Verify
    from app.services.payments import submit_payment, verify
    from app.services.publishing import publish

    article, invoice, proof, final, admin = approved(pg)
    author = pg.get(User, article.author_id)
    attempt = submit_payment(
        pg,
        invoice.id,
        author,
        PaymentInput(
            amount_minor=invoice.amount_minor,
            reference="NOTIFY123",
            paid_at=db_now(pg) - timedelta(minutes=1),
            proof_file_id=proof.id,
        ),
    )
    verify(
        pg,
        attempt.id,
        admin,
        Verify(
            reference="NOTIFY123",
            receipt_note="Actual bank receipt checked",
            receipt_confirmed=True,
        ),
    )
    publish(
        pg,
        article.id,
        admin,
        Publish(
            approved_version_id=article.approved_version_id,
            final_file_id=final.id,
            slug="notification-test",
            title="Published research",
            public_authors=["Author"],
        ),
    )
    pg.commit()
    kinds = set(pg.scalars(select(Notification.type).where(Notification.recipient_id == author.id)))
    assert {
        "ASSIGNED",
        "ARTICLE_APPROVED",
        "PAYMENT_SUBMITTED",
        "PAYMENT_VERIFIED",
        "PUBLISHED",
    } <= kinds
    assert pg.scalar(
        select(Notification.id).where(
            Notification.recipient_id == admin.id, Notification.type == "PAYMENT_SUBMITTED"
        )
    )
    assert (
        pg.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_id == author.id, Notification.read_at.is_(None))
        )
        >= 5
    )
