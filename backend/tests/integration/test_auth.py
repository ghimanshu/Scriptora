from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.secrets import unseal
from app.db import session
from app.main import app
from app.models.notifications import OutboxEvent
from app.models.users import OneTimeToken


def test_registration_verification_and_refresh_replay(pg, pg_engine, monkeypatch):
    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    with TestClient(app) as client:
        credentials = {
            "email": "new-author@example.com",
            "password": "a sufficiently long test password",
        }
        response = client.post(
            "/api/v1/auth/register", json={**credentials, "display_name": "New author"}
        )
        assert response.status_code == 201, response.text
        event = pg.scalar(select(OutboxEvent).where(OutboxEvent.type == "VERIFY_EMAIL"))
        assert "token" not in event.payload
        token = unseal(event.payload["encrypted_token"])
        stored = pg.scalar(select(OneTimeToken))
        assert stored.token_hash != token
        assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 204
        assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400
        response = client.post("/api/v1/auth/login", json=credentials)
        assert response.status_code == 200, response.text
        initial = response.json()
        renewed = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": initial["refresh_token"]}
        )
        assert renewed.status_code == 200
        replay = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": initial["refresh_token"]}
        )
        assert replay.status_code == 401
        assert (
            client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + renewed.json()["access_token"]}
            ).status_code
            == 401
        )
