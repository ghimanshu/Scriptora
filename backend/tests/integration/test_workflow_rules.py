import uuid
from datetime import timedelta
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_workflow import setup_article

from app.core.security import issue_session
from app.db import session
from app.models.articles import ArticleVersion, File
from app.models.reviews import Assignment
from app.models.users import User, UserRole


def headers(db, user):
    return {
        "Authorization": "Bearer " + issue_session(db, user)["access_token"],
        "Idempotency-Key": str(uuid.uuid4()),
    }


def test_draft_private_in_lists_details_versions_activity_and_files(pg, pg_engine, monkeypatch):
    from app.api.v1 import files
    from app.main import app

    article, reviewers = setup_article(pg)
    author = pg.get(User, article.author_id)
    admin = reviewers[1]
    pg.add(UserRole(user_id=admin.id, role="ADMIN"))
    article.status = "DRAFT"
    version = pg.get(ArticleVersion, article.current_version_id)
    version.submitted_at = None
    manuscript = File(
        owner_user_id=author.id,
        kind="MANUSCRIPT",
        storage_key="private-draft",
        sha256="a" * 64,
        size_bytes=1,
        content_type="application/pdf",
        scan_status="CLEAN",
    )
    pg.add(manuscript)
    pg.flush()
    version.manuscript_file_id = manuscript.id
    own, editorial, reviewer = headers(pg, author), headers(pg, admin), headers(pg, reviewers[0])
    pg.commit()
    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    monkeypatch.setattr(files, "storage", lambda: Mock(get=lambda _: b"%PDF"))
    with TestClient(app) as client:
        for actor in (editorial, reviewer):
            for suffix in ("", "/versions", "/timeline"):
                assert (
                    client.get(f"/api/v1/articles/{article.id}{suffix}", headers=actor).status_code
                    == 404
                )
            assert (
                client.get(f"/api/v1/files/{manuscript.id}/download", headers=actor).status_code
                == 404
            )
        assert client.get("/api/v1/admin/articles", headers=editorial).json()["items"] == []
        assert client.get(f"/api/v1/articles/{article.id}", headers=own).status_code == 200
        assert client.get(f"/api/v1/files/{manuscript.id}/download", headers=own).status_code == 200


def test_admin_assignment_and_claim_share_exclusive_five_day_lease(pg, pg_engine, monkeypatch):
    from app.main import app

    article, reviewers = setup_article(pg)
    admin = reviewers[1]
    author = pg.get(User, article.author_id)
    pg.add(UserRole(user_id=admin.id, role="ADMIN"))
    editorial, reviewer, own = headers(pg, admin), headers(pg, reviewers[0]), headers(pg, author)
    pg.commit()
    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    with TestClient(app) as client:
        assert client.get(f"/api/v1/articles/{article.id}", headers=reviewer).status_code == 200
        candidates = client.get(f"/api/v1/admin/articles/{article.id}/reviewers", headers=editorial)
        assert candidates.status_code == 200
        assert str(reviewers[0].id) in [row["id"] for row in candidates.json()["items"]]
        url = f"/api/v1/admin/articles/{article.id}/assign"
        body = {
            "reviewer_id": str(reviewers[0].id),
            "reason": "Matching expertise",
            "expected_version": article.lock_version,
        }
        assert client.post(url, headers=own, json=body).status_code == 403
        response = client.post(url, headers=editorial, json=body)
        assert response.status_code == 200, response.text
        pg.expire_all()
        assignment = pg.scalar(select(Assignment))
        assert assignment.due_at - assignment.assigned_at == timedelta(days=5)
        assert article.status == "ASSIGNED"
        detail = client.get(f"/api/v1/articles/{article.id}", headers=editorial).json()
        assert "ASSIGN" not in detail["allowed_actions"]
        body["expected_version"] = detail["lock_version"]
        body["reviewer_id"] = str(admin.id)
        editorial["Idempotency-Key"] = str(uuid.uuid4())
        assert client.post(url, headers=editorial, json=body).status_code == 409
        assert (
            client.post(
                f"/api/v1/articles/{article.id}/claim",
                headers=editorial,
                json={"expected_version": detail["lock_version"]},
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/v1/admin/assignments/{assignment.id}/extend",
                headers=editorial,
                json={
                    "new_due_at": (assignment.due_at + timedelta(days=1)).isoformat(),
                    "reason": "Try extension",
                },
            ).status_code
            == 409
        )
