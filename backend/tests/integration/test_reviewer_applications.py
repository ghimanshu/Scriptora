import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.db import session
from app.db.session import db_now
from app.main import app
from app.models.notifications import EmailDelivery, Notification, OutboxEvent
from app.models.users import User, UserRole
from app.workers import outbox


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_application_admin_notification_and_reviewer_decision(pg, pg_engine, monkeypatch, decision):
    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    sent = []
    monkeypatch.setattr(
        outbox, "send_email", lambda email, subject, body: sent.append((email, subject, body))
    )
    admin = User(
        email="admin@example.com",
        display_name="Admin",
        password_hash=hash_password("admin long password"),
        email_verified_at=db_now(pg),
    )
    pg.add(admin)
    pg.flush()
    pg.add(UserRole(user_id=admin.id, role="ADMIN"))
    pg.commit()
    with TestClient(app) as client:
        credentials = {"email": "reviewer@example.com", "password": "reviewer long password"}
        response = client.post(
            "/api/v1/auth/register",
            json={**credentials, "display_name": "New Reviewer", "role": "REVIEWER"},
        )
        assert response.status_code == 201, response.text
        event = pg.scalar(select(OutboxEvent))
        assert event.type == "REVIEWER_APPLICATION"
        assert event.payload["recipients"] == [str(admin.id)]
        assert "encrypted_token" not in event.payload
        assert client.post("/api/v1/auth/login", json=credentials).status_code == 403
        outbox.run()
        assert [email for email, _, _ in sent] == [admin.email]
        assert pg.scalar(select(Notification.recipient_id)) == admin.id
        token = client.post(
            "/api/v1/auth/login", json={"email": admin.email, "password": "admin long password"}
        ).json()["access_token"]
        headers = {"Authorization": "Bearer " + token, "Idempotency-Key": str(uuid.uuid4())}
        queue = client.get("/api/v1/admin/reviewers", headers=headers).json()["items"]
        assert len(queue) == 1
        assert queue[0]["email_verified"] is False
        reviewer_id = queue[0]["id"]
        url = f"/api/v1/admin/reviewers/{reviewer_id}/{decision}"
        result = client.post(url, headers=headers, json={"reason": "Qualifications reviewed"})
        assert result.status_code == 200, result.text
        assert (
            client.post(url, headers=headers, json={"reason": "Qualifications reviewed"}).json()
            == result.json()
        )
        assert client.get("/api/v1/admin/reviewers", headers=headers).json()["items"] == []
        outbox.run()
        assert [email for email, _, _ in sent] == [admin.email, credentials["email"]]
        assert "Qualifications reviewed" in sent[-1][2]
        assert len(list(pg.scalars(select(EmailDelivery)))) == 2
        if decision == "approve":
            approval = pg.scalar(select(OutboxEvent).where(OutboxEvent.type == "REVIEWER_APPROVED"))
            # Delivery scrubs encrypted tokens; read the verification token from the captured email.
            pg.refresh(approval)
            assert "encrypted_token" not in approval.payload
            raw = sent[-1][2].split("?token=")[-1].strip()
            assert raw
            assert client.post("/api/v1/auth/verify-email", json={"token": raw}).status_code == 204
            assert client.post("/api/v1/auth/login", json=credentials).status_code == 200
        else:
            response = client.post("/api/v1/auth/login", json=credentials)
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == "REVIEWER_APPLICATION_REJECTED"
