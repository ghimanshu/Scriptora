from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.cli import seed
from app.db.session import db_now
from app.models.articles import Article, ArticleVersion
from app.models.payments import Invoice
from app.models.reviews import Assignment, ReviewRound
from app.models.taxonomy import Outlet, SettingsVersion, Subject, Template
from app.models.users import ReviewerProfile, ReviewerSubject, User, UserRole
from app.schemas.reviews import Feedback
from app.services.assignments import claim, lock_assignment
from app.services.reviews import save_review


def setup_article(db):
    seed(db)
    db.flush()
    subject = db.scalar(select(Subject))
    outlet = db.scalar(select(Outlet))
    template = db.scalar(select(Template).where(Template.outlet_id == outlet.id))
    policy = db.scalar(select(SettingsVersion))
    policy.values = {
        **policy.values,
        "publication_fee_minor": 250000,
        "review_duration_hours": 120,
        "payment_instructions": "Test bank account only",
    }
    author = User(
        email="author@example.com",
        display_name="Author",
        password_hash="unused",
        email_verified_at=db_now(db),
    )
    db.add(author)
    db.flush()
    reviewers = []
    for i in range(2):
        user = User(
            email=f"reviewer{i}@example.com",
            display_name="Reviewer",
            password_hash="unused",
            email_verified_at=db_now(db),
        )
        db.add(user)
        db.flush()
        db.add_all(
            [
                UserRole(user_id=user.id, role="REVIEWER"),
                ReviewerProfile(user_id=user.id, approved=True),
                ReviewerSubject(reviewer_id=user.id, subject_id=subject.id),
            ]
        )
        reviewers.append(user)
    article = Article(
        tracking_number="TEST-1",
        author_id=author.id,
        primary_subject_id=subject.id,
        outlet_id=outlet.id,
        template_id=template.id,
        status="SUBMITTED",
    )
    db.add(article)
    db.flush()
    version = ArticleVersion(
        article_id=article.id,
        version_number=1,
        template_id=template.id,
        data={"title": "Test article"},
        submitted_at=db_now(db),
    )
    db.add(version)
    db.flush()
    round = ReviewRound(article_id=article.id, version_id=version.id, round_number=1)
    db.add(round)
    db.flush()
    article.current_version_id, article.current_round_id = version.id, round.id
    db.commit()
    return article, reviewers


def test_migration_revision_and_constraints(pg):
    assert (
        pg.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        == "0009_draft_subjects"
    )
    indexes = set(pg.scalars(text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")))
    assert {
        "uq_article_live_assignment",
        "uq_verified_payment_reference",
        "uq_pending_invoice_payment",
    } <= indexes


def test_two_claimants_exactly_one_wins(pg, pg_engine):
    article, reviewers = setup_article(pg)
    article_id, version = article.id, article.lock_version
    barrier = Barrier(2)

    def attempt(user_id):
        with Session(pg_engine, expire_on_commit=False) as db:
            user = db.get(User, user_id)
            barrier.wait(timeout=10)
            try:
                assignment = claim(db, article_id, user, version)
                db.commit()
                return str(assignment.id)
            except HTTPException as error:
                db.rollback()
                assert error.status_code == 409
                return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, [r.id for r in reviewers]))
    assert sum(result is not None for result in results) == 1
    pg.expire_all()
    assignment = pg.scalar(select(Assignment))
    assert assignment.due_at - assignment.assigned_at == timedelta(hours=120)


def test_late_review_expires_without_worker(pg):
    article, reviewers = setup_article(pg)
    assignment = claim(pg, article.id, reviewers[0], article.lock_version)
    pg.commit()
    assignment.assigned_at = db_now(pg) - timedelta(days=6)
    assignment.due_at = db_now(pg) - timedelta(seconds=1)
    pg.commit()
    try:
        lock_assignment(pg, assignment.id, reviewers[0])
        raise AssertionError("late review admitted")
    except HTTPException as error:
        assert error.detail["code"] == "ASSIGNMENT_EXPIRED"
    pg.refresh(assignment)
    assert assignment.state == "EXPIRED"
    pg.refresh(article)
    assert article.status == "SUBMITTED"


def test_approval_issues_single_snapshot_invoice(pg):
    article, reviewers = setup_article(pg)
    assignment = claim(pg, article.id, reviewers[0], article.lock_version)
    pg.commit()
    data = Feedback(
        decision="APPROVE",
        comments="Accepted",
        checklist={"format": True},
        required_changes_resolved=True,
    )
    save_review(pg, assignment.id, reviewers[0], data)
    pg.commit()
    invoice = pg.scalar(select(Invoice))
    assert invoice.amount_minor == 250000
    assert invoice.approved_version_id == article.current_version_id
    assert article.status == "APPROVED"
    try:
        save_review(pg, assignment.id, reviewers[0], data)
        raise AssertionError("duplicate approval admitted")
    except HTTPException:
        pg.rollback()
    assert len(list(pg.scalars(select(Invoice)))) == 1


def test_author_edit_actions_and_submission_lock(pg, pg_engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.security import issue_session
    from app.db import session
    from app.main import app

    article, _ = setup_article(pg)
    author = pg.get(User, article.author_id)
    tokens = issue_session(pg, author)
    pg.commit()
    monkeypatch.setattr(session, "engine", lambda: pg_engine)
    headers = {
        "Authorization": "Bearer " + tokens["access_token"],
        "If-Match": str(article.lock_version),
        "Idempotency-Key": "locked-edit",
    }
    with TestClient(app) as client:
        url = f"/api/v1/articles/{article.id}"
        response = client.get(url, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["allowed_actions"] == []
        assert response.json()["title"] == "Test article"
        response = client.patch(url, headers=headers, json={"metadata": {"title": "Blocked edit"}})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "DRAFT_REQUIRED"
        article.status = "DRAFT"
        version = pg.get(ArticleVersion, article.current_version_id)
        version.submitted_at = None
        pg.commit()
        assert client.get(url, headers=headers).json()["allowed_actions"] == ["EDIT", "SUBMIT"]
        headers["Idempotency-Key"] = "draft-edit"
        response = client.patch(
            url,
            headers=headers,
            json={"metadata": {"title": "Updated draft", "abstract": "Updated abstract"}},
        )
        assert response.status_code == 200, response.text
        detail = client.get(url, headers=headers).json()
        assert detail["title"] == "Updated draft"
        assert detail["abstract"] == "Updated abstract"
        assert detail["lock_version"] == article.lock_version + 1
