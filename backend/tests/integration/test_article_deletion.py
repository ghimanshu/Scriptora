import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from test_workflow import setup_article

from app.core.security import issue_session
from app.db import session
from app.db.session import db_now
from app.main import app
from app.models.articles import Article, ArticleVersion, File
from app.models.audit import AuditEvent
from app.models.notifications import EmailDelivery, Notification, OutboxEvent
from app.models.payments import Invoice, Publication
from app.models.reviews import Assignment, StatusHistory
from app.models.users import User, UserRole
from app.services.assignments import claim
from app.workers import outbox


@pytest.mark.parametrize(
    "stage", ["DRAFT", "SUBMITTED", "ASSIGNED", "REJECTED", "APPROVED", "PUBLISH"]
)
def test_admin_can_delete_any_stage_and_notify_author(pg, pg_engine, monkeypatch, stage):
    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    article, reviewers = setup_article(pg)
    assignment = claim(pg, article.id, reviewers[0], article.lock_version)
    article.status = stage
    admin = reviewers[1]
    author = pg.get(User, article.author_id)
    pg.add(UserRole(user_id=admin.id, role="ADMIN"))
    file = File(
        owner_user_id=author.id,
        kind="MANUSCRIPT",
        storage_key=uuid.uuid4().hex,
        sha256="a" * 64,
        size_bytes=1,
        content_type="application/pdf",
        scan_status="CLEAN",
    )
    pg.add(file)
    pg.flush()
    pg.get(ArticleVersion, article.current_version_id).manuscript_file_id = file.id
    invoice = None
    publication = None
    if stage in ("APPROVED", "PUBLISH"):
        article.approved_version_id = article.current_version_id
        invoice = Invoice(
            article_id=article.id,
            approved_version_id=article.current_version_id,
            invoice_number="TEST-INVOICE",
            amount_minor=100,
            currency="INR",
            fee_policy_version=1,
            instructions="Test bank",
            status="PAID" if stage == "PUBLISH" else "OPEN",
        )
        pg.add(invoice)
    if stage == "PUBLISH":
        publication = Publication(
            article_id=article.id,
            version_id=article.current_version_id,
            slug="deleted-article",
            final_file_id=file.id,
            published_by=admin.id,
            published_at=db_now(pg),
            data={"title": "Test article"},
        )
        pg.add(publication)
    admin_token = issue_session(pg, admin)["access_token"]
    author_token = issue_session(pg, author)["access_token"]
    pg.execute(delete(OutboxEvent))
    pg.commit()
    headers = {"Authorization": "Bearer " + admin_token, "Idempotency-Key": str(uuid.uuid4())}
    author_headers = {
        "Authorization": "Bearer " + author_token,
        "Idempotency-Key": str(uuid.uuid4()),
    }
    url = f"/api/v1/admin/articles/{article.id}"
    reason = "Duplicate manuscript submitted in error"
    sent = []
    monkeypatch.setattr(outbox, "send_email", lambda *args: sent.append(args))
    with TestClient(app) as client:
        assert (
            client.request(
                "DELETE", url, headers=author_headers, json={"reason": reason}
            ).status_code
            == 403
        )
        for payload in ({}, {"reason": "   "}, {"reason": "ab"}, {"reason": "x" * 2001}):
            assert client.request("DELETE", url, headers=headers, json=payload).status_code == 422
        result = client.request(
            "DELETE", url, headers=headers, json={"reason": "  " + reason + "  "}
        )
        assert result.status_code == 200, result.text
        assert result.json() == {"deleted": True, "article_id": str(article.id)}
        assert (
            client.request(
                "DELETE", url, headers=headers, json={"reason": "  " + reason + "  "}
            ).json()
            == result.json()
        )
        assert (
            client.request(
                "DELETE",
                url,
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={"reason": reason},
            ).status_code
            == 404
        )
        for who in (headers, author_headers):
            for suffix in ("", "/versions", "/timeline"):
                assert (
                    client.get(f"/api/v1/articles/{article.id}" + suffix, headers=who).status_code
                    == 404
                )
            assert client.get(f"/api/v1/files/{file.id}/download", headers=who).status_code == 404
        assert client.get("/api/v1/admin/articles", headers=headers).json()["items"] == []
        assert client.get("/api/v1/articles", headers=author_headers).json()["items"] == []
        assert client.get("/api/v1/public/articles").json()["items"] == []
        if publication:
            for suffix in ("", "/download"):
                assert (
                    client.get("/api/v1/public/articles/deleted-article" + suffix).status_code
                    == 404
                )
        assert (
            client.post(
                f"/api/v1/articles/{article.id}/claim",
                headers=headers,
                json={"expected_version": article.lock_version},
            ).status_code
            == 404
        )
    pg.expire_all()
    assert pg.get(Article, article.id).status == "DELETED"
    assert pg.get(Assignment, assignment.id).state == "REVOKED"
    assert pg.get(Assignment, assignment.id).end_reason == reason
    if invoice:
        assert pg.get(Invoice, invoice.id).status == ("PAID" if stage == "PUBLISH" else "VOID")
    if publication:
        assert pg.get(Publication, publication.id) is not None
    event = pg.scalar(select(OutboxEvent).where(OutboxEvent.type == "ARTICLE_DELETED"))
    assert event.payload["recipients"] == [str(author.id)]
    assert event.payload["reason"] == reason
    audit = pg.scalar(select(AuditEvent).where(AuditEvent.action == "ARTICLE_DELETED"))
    assert audit.actor_id == admin.id and audit.data["reason"] == reason
    assert (
        pg.scalar(select(StatusHistory).where(StatusHistory.new_status == "DELETED")).reason
        == reason
    )
    # Even an inactive author must receive the deletion email.
    author.active = False
    pg.commit()
    outbox.run()
    outbox.run()
    assert len(sent) == 1
    assert sent[0][0] == author.email
    assert (
        reason in sent[0][2]
        and article.tracking_number in sent[0][2]
        and "Test article" in sent[0][2]
    )
    assert len(list(pg.scalars(select(EmailDelivery)))) == 1
    assert (
        pg.scalar(select(Notification).where(Notification.type == "ARTICLE_DELETED")).recipient_id
        == author.id
    )


def test_deletion_rolls_back_when_notification_cannot_be_queued(pg, pg_engine, monkeypatch):
    from app.services import article_deletion

    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    article, reviewers = setup_article(pg)
    admin = reviewers[1]
    pg.add(UserRole(user_id=admin.id, role="ADMIN"))
    token = issue_session(pg, admin)["access_token"]
    pg.commit()

    def reject_queue(*args, **kwargs):
        raise RuntimeError("Queue unavailable")

    monkeypatch.setattr(article_deletion, "emit", reject_queue)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.request(
            "DELETE",
            f"/api/v1/admin/articles/{article.id}",
            headers={"Authorization": "Bearer " + token, "Idempotency-Key": str(uuid.uuid4())},
            json={"reason": "Duplicate submission"},
        )
        assert response.status_code == 500
    pg.expire_all()
    assert pg.get(Article, article.id).status == "SUBMITTED"
    assert pg.scalar(select(AuditEvent).where(AuditEvent.action == "ARTICLE_DELETED")) is None
    assert pg.scalar(select(StatusHistory).where(StatusHistory.new_status == "DELETED")) is None


def test_concurrent_deletions_queue_one_author_email(pg, pg_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fastapi import HTTPException
    from sqlalchemy.orm import Session

    from app.services.article_deletion import remove

    article, reviewers = setup_article(pg)
    article_id, actor_id = article.id, reviewers[1].id
    barrier = Barrier(2)

    def attempt():
        with Session(pg_engine) as db:
            actor = db.get(User, actor_id)
            barrier.wait(timeout=10)
            try:
                remove(db, article_id, actor, "Duplicate submission")
                db.commit()
                return 200
            except HTTPException as error:
                db.rollback()
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == [200, 404]
    assert (
        len(list(pg.scalars(select(OutboxEvent).where(OutboxEvent.type == "ARTICLE_DELETED")))) == 1
    )
    assert (
        len(list(pg.scalars(select(AuditEvent).where(AuditEvent.action == "ARTICLE_DELETED")))) == 1
    )
