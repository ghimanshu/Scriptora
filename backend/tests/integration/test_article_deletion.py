import uuid

import pytest
from fastapi.testclient import TestClient
from test_workflow import setup_article

from app.core.security import issue_session
from app.db import session
from app.main import app
from app.models.articles import Article
from app.models.users import User, UserRole


@pytest.mark.parametrize(
    "status",
    [
        "DRAFT",
        "SUBMITTED",
        "ASSIGNED",
        "REJECTED",
        "APPROVED",
        "PAID",
        "PAYMENT_APPROVED",
        "PUBLISH",
    ],
)
def test_only_owner_can_delete_only_a_draft(pg, pg_engine, monkeypatch, status):
    article, reviewers = setup_article(pg)
    article.status = status
    author = pg.get(User, article.author_id)
    admin = reviewers[1]
    pg.add(UserRole(user_id=admin.id, role="ADMIN"))
    own = {
        "Authorization": "Bearer " + issue_session(pg, author)["access_token"],
        "Idempotency-Key": str(uuid.uuid4()),
    }
    other = {
        "Authorization": "Bearer " + issue_session(pg, admin)["access_token"],
        "Idempotency-Key": str(uuid.uuid4()),
    }
    pg.commit()
    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    url = f"/api/v1/articles/{article.id}"
    body = {"reason": "Draft removed by its author."}
    with TestClient(app) as client:
        assert client.request("DELETE", url, headers=other, json=body).status_code == 404
        assert (
            client.request(
                "DELETE", f"/api/v1/admin/articles/{article.id}", headers=other, json=body
            ).status_code
            == 404
        )
        result = client.request("DELETE", url, headers=own, json=body)
        assert result.status_code == (200 if status == "DRAFT" else 409), result.text
        pg.expire_all()
        assert pg.get(Article, article.id).status == ("DELETED" if status == "DRAFT" else status)
        if status == "DRAFT":
            assert client.request("DELETE", url, headers=own, json=body).json() == result.json()
            assert client.get(url, headers=own).status_code == 404
            assert client.get("/api/v1/articles", headers=own).json()["items"] == []
