import uuid

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_workflow import setup_article

from app.core.security import issue_session
from app.db import session
from app.main import app
from app.models.articles import Article, ArticleSubject, ArticleVersion
from app.models.taxonomy import Outlet, PublicationType, Subject, Template
from app.models.users import User, UserRole


def setup_client(db, pg_engine, monkeypatch):
    original, _ = setup_article(db)
    author = db.get(User, original.author_id)
    db.add(UserRole(user_id=author.id, role="AUTHOR"))
    token = issue_session(db, author)["access_token"]
    outlet = db.get(Outlet, original.outlet_id)
    body = {
        "publication_type_id": str(outlet.type_id),
        "outlet_id": str(outlet.id),
        "template_id": str(original.template_id),
        "metadata": {},
    }
    db.commit()
    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": str(uuid.uuid4())}
    return original, body, headers


def test_draft_saves_publication_then_subject_and_keeps_them_on_metadata_edits(
    pg, pg_engine, monkeypatch
):
    original, body, headers = setup_client(pg, pg_engine, monkeypatch)
    with TestClient(app) as client:
        response = client.post("/api/v1/articles", headers=headers, json=body)
        assert response.status_code == 201, response.text
        draft_id = uuid.UUID(response.json()["id"])
        pg.expire_all()
        draft = pg.get(Article, draft_id)
        assert draft.status == "DRAFT"
        assert draft.primary_subject_id is None
        assert str(draft.outlet_id) == body["outlet_id"]
        assert str(draft.template_id) == body["template_id"]
        assert str(pg.get(Outlet, draft.outlet_id).type_id) == body["publication_type_id"]
        assert not pg.get(ArticleSubject, (draft.id, original.primary_subject_id))
        url = f"/api/v1/articles/{draft.id}"
        detail = client.get(url, headers=headers).json()
        assert detail["publication_type_id"] == body["publication_type_id"]
        headers.update({"If-Match": str(draft.lock_version), "Idempotency-Key": str(uuid.uuid4())})
        update = {
            **body,
            "primary_subject_id": str(original.primary_subject_id),
            "metadata": {"title": "Saved manuscript", "abstract": "Saved abstract"},
        }
        response = client.patch(url, headers=headers, json=update)
        assert response.status_code == 200, response.text
        pg.expire_all()
        draft = pg.get(Article, draft_id)
        assert draft.primary_subject_id == original.primary_subject_id
        assert pg.get(ArticleSubject, (draft.id, draft.primary_subject_id))
        version = pg.get(ArticleVersion, draft.current_version_id)
        assert version.template_id == draft.template_id
        assert version.data["title"] == "Saved manuscript"
        headers.update({"If-Match": str(draft.lock_version), "Idempotency-Key": str(uuid.uuid4())})
        response = client.patch(url, headers=headers, json={"metadata": {"title": "Another edit"}})
        assert response.status_code == 200, response.text
        assert response.json()["primary_subject_id"] == str(original.primary_subject_id)


def test_subject_change_and_first_tab_changes_are_persisted_and_validated(
    pg, pg_engine, monkeypatch
):
    original, body, headers = setup_client(pg, pg_engine, monkeypatch)
    subject = Subject(slug="second-subject", name="Second subject")
    kind = PublicationType(code="SECOND", name="Second publication type")
    pg.add_all([subject, kind])
    pg.flush()
    outlet = Outlet(slug="second-outlet", name="Second outlet", type_id=kind.id)
    pg.add(outlet)
    pg.flush()
    template = Template(outlet_id=outlet.id, version=1, validation_schema={})
    pg.add(template)
    pg.commit()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/articles",
            headers=headers,
            json={**body, "primary_subject_id": str(original.primary_subject_id)},
        )
        assert response.status_code == 201, response.text
        draft_id = uuid.UUID(response.json()["id"])
        assert pg.get(ArticleSubject, (draft_id, original.primary_subject_id))
        url = f"/api/v1/articles/{draft_id}"
        headers.update({"If-Match": "1", "Idempotency-Key": str(uuid.uuid4())})
        update = {
            "primary_subject_id": str(subject.id),
            "publication_type_id": str(kind.id),
            "outlet_id": str(outlet.id),
            "template_id": str(template.id),
            "metadata": {"title": "Updated"},
        }
        assert client.patch(url, headers=headers, json=update).status_code == 200
        pg.expire_all()
        draft = pg.get(Article, draft_id)
        assert draft.primary_subject_id == subject.id
        assert draft.outlet_id == outlet.id
        assert draft.template_id == template.id
        assert pg.get(ArticleVersion, draft.current_version_id).template_id == template.id
        assert pg.get(ArticleSubject, (draft_id, subject.id))
        assert not pg.get(ArticleSubject, (draft_id, original.primary_subject_id))
        headers.update({"If-Match": str(draft.lock_version), "Idempotency-Key": str(uuid.uuid4())})
        assert (
            client.patch(
                url,
                headers=headers,
                json={**update, "publication_type_id": body["publication_type_id"]},
            ).status_code
            == 422
        )
        headers["Idempotency-Key"] = str(uuid.uuid4())
        assert (
            client.patch(
                url, headers=headers, json={**update, "primary_subject_id": str(uuid.uuid4())}
            ).status_code
            == 422
        )


def test_subjectless_draft_cannot_be_submitted(pg, pg_engine, monkeypatch):
    _, body, headers = setup_client(pg, pg_engine, monkeypatch)
    with TestClient(app) as client:
        response = client.post("/api/v1/articles", headers=headers, json=body)
        assert response.status_code == 201
        headers["Idempotency-Key"] = str(uuid.uuid4())
        response = client.post(
            f"/api/v1/articles/{response.json()['id']}/submit",
            headers=headers,
            json={"expected_version": 1},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "SUBJECT_REQUIRED"


def test_migration_backfills_existing_primary_subject_links(pg, pg_engine):
    article, _ = setup_article(pg)
    article_id, subject_id = article.id, article.primary_subject_id
    assert pg.get(ArticleSubject, (article_id, subject_id)) is None
    pg.close()
    config = Config("alembic.ini")
    command.downgrade(config, "0008_article_workflow")
    try:
        command.upgrade(config, "head")
        assert pg.get(ArticleSubject, (article_id, subject_id)) is not None
    finally:
        pg.close()
        command.upgrade(config, "head")


def test_migration_refuses_to_discard_subjectless_drafts_on_downgrade(pg, pg_engine, monkeypatch):
    _, body, headers = setup_client(pg, pg_engine, monkeypatch)
    with TestClient(app) as client:
        assert client.post("/api/v1/articles", headers=headers, json=body).status_code == 201
    pg.close()
    with pytest.raises(RuntimeError, match="Select a subject"):
        command.downgrade(Config("alembic.ini"), "0008_article_workflow")
    with pg_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0009_draft_subjects"
        )
