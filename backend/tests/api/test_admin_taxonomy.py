from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import admin, current_user, database
from app.main import app
from app.models.taxonomy import Issue, Outlet, Subject, Template

RESOURCES = [
    ("subjects", Subject, {"slug": "science", "name": "Science", "active": False}),
    (
        "outlets",
        Outlet,
        {"type_id": uuid4(), "slug": "journal", "name": "Journal", "active": False},
    ),
    (
        "templates",
        Template,
        {
            "outlet_id": uuid4(),
            "version": 1,
            "validation_schema": {},
            "instructions": "Instructions",
            "active": False,
        },
    ),
    (
        "issues",
        Issue,
        {"outlet_id": uuid4(), "volume": "1", "issue_number": "2", "label": "Issue 2"},
    ),
]


@pytest.mark.parametrize("resource,model,values", RESOURCES)
def test_admin_taxonomy_requires_authentication(resource, model, values):
    with TestClient(app) as client:
        assert client.get(f"/api/v1/admin/{resource}").status_code == 401


@pytest.mark.parametrize("resource,model,values", RESOURCES)
def test_admin_taxonomy_rejects_non_admin(resource, model, values):
    db = Mock()
    db.scalars.return_value = ["AUTHOR"]
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[database] = lambda: db
    try:
        with TestClient(app) as client:
            assert client.get(f"/api/v1/admin/{resource}").status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("resource,model,values", RESOURCES)
def test_admin_taxonomy_lists_records_and_paginates(resource, model, values):
    rows = [model(id=uuid4(), created_at=datetime.now(UTC), **values) for _ in range(2)]
    db = Mock()
    db.scalars.side_effect = [rows, rows[1:], []]
    app.dependency_overrides[admin] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[database] = lambda: db
    try:
        with TestClient(app) as client:
            url = f"/api/v1/admin/{resource}"
            first = client.get(url, params={"limit": 1})
            assert first.status_code == 200, first.text
            body = first.json()
            assert body["items"][0]["id"] == str(rows[0].id)
            if "active" in values:
                assert body["items"][0]["active"] is False
            assert body["next_cursor"]
            second = client.get(url, params={"limit": 1, "cursor": body["next_cursor"]})
            assert second.status_code == 200, second.text
            assert second.json()["items"][0]["id"] == str(rows[1].id)
            assert second.json()["next_cursor"] is None
            assert "WHERE" in str(db.scalars.call_args.args[0])
            assert client.get(url).json() == {"items": [], "next_cursor": None}
            for limit in (0, 101):
                assert client.get(url, params={"limit": limit}).status_code == 422
            assert client.get(url, params={"cursor": "invalid"}).status_code == 422
    finally:
        app.dependency_overrides.clear()
