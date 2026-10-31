import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_workflow import setup_article

from app.core.security import issue_session
from app.db import session
from app.main import app
from app.models.articles import Article
from app.models.taxonomy import Template
from app.models.users import User, UserRole


def test_command_retry_and_payload_mismatch(pg, pg_engine, monkeypatch):
    article, _ = setup_article(pg)
    from app.models.users import User

    author = pg.get(User, article.author_id)
    pg.add(UserRole(user_id=author.id, role="AUTHOR"))
    token = issue_session(pg, author)["access_token"]
    pg.commit()
    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": str(uuid.uuid4())}
    template = pg.get(Template, article.template_id)
    body = {
        "primary_subject_id": str(article.primary_subject_id),
        "outlet_id": str(article.outlet_id),
        "template_id": str(template.id),
        "metadata": {"title": "A new draft"},
    }
    with TestClient(app) as client:
        first = client.post("/api/v1/articles", json=body, headers=headers)
        assert first.status_code == 201, first.text
        second = client.post("/api/v1/articles", json=body, headers=headers)
        assert second.status_code == 201
        assert first.json() == second.json()
        body["metadata"]["title"] = "Changed payload"
        assert client.post("/api/v1/articles", json=body, headers=headers).status_code == 409
    assert len(list(pg.scalars(select(Article)))) == 2


def test_article_list_includes_current_version_title(pg, pg_engine, monkeypatch):
    article, _ = setup_article(pg)
    author = pg.get(User, article.author_id)
    pg.add(UserRole(user_id=author.id, role="AUTHOR"))
    token = issue_session(pg, author)["access_token"]
    pg.commit()
    monkeypatch.setattr(session, "engine", lambda: pg_engine)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/articles",
            headers={"Authorization": "Bearer " + token},
        )

    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["title"] == "Test article"
