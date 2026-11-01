from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import admin, current_user, database
from app.main import app
from app.models.audit import AuditEvent


def test_audit_events_requires_admin():
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/audit-events?search=&cursor=").status_code == 401
        app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=uuid4())
        db = Mock()
        db.scalars.return_value = ["AUTHOR"]
        app.dependency_overrides[database] = lambda: db
        try:
            assert client.get("/api/v1/admin/audit-events").status_code == 403
        finally:
            app.dependency_overrides.clear()


def test_audit_events_search_pagination_and_display_fields():
    actor = SimpleNamespace(id=uuid4(), display_name="Admin")
    rows = [
        AuditEvent(
            id=uuid4(),
            created_at=datetime.now(UTC),
            actor_id=actor.id,
            action="APPROVE_REVIEWER",
            entity_type="User",
            entity_id=uuid4(),
            request_id="request-1",
            data={"private": "hidden"},
        )
        for _ in range(2)
    ]
    rows[1].actor_id = None
    db = Mock()
    db.scalars.side_effect = [rows, [actor], rows[1:], []]
    app.dependency_overrides[admin] = lambda: actor
    app.dependency_overrides[database] = lambda: db
    try:
        with TestClient(app) as client:
            url = "/api/v1/admin/audit-events"
            first = client.get(url, params={"search": "APPROVE_%", "limit": 1, "cursor": ""})
            assert first.status_code == 200, first.text
            body = first.json()
            item = body["items"][0]
            assert item["event_type"] == "APPROVE_REVIEWER"
            assert item["actor_name"] == "Admin"
            assert str(rows[0].entity_id) in item["summary"]
            assert "data" not in item
            query = db.scalars.call_args_list[0].args[0].compile()
            assert "WHERE" in str(query)
            assert "APPROVE/_/%" in query.params.values()
            second = client.get(
                url, params={"search": "APPROVE_%", "limit": 1, "cursor": body["next_cursor"]}
            )
            assert second.status_code == 200, second.text
            assert second.json()["items"][0]["actor_name"] is None
            assert second.json()["next_cursor"] is None
            assert client.get(url + "?search=&cursor=").json() == {"items": [], "next_cursor": None}
            assert client.get(url, params={"cursor": "invalid"}).status_code == 422
            assert client.get(url, params={"limit": 101}).status_code == 422
            assert client.get(url, params={"search": "a" * 201}).status_code == 422
    finally:
        app.dependency_overrides.clear()
