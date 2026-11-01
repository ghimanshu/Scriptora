import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from test_workflow import setup_article

from app.db.session import db_now
from app.models.articles import ArticleVersion, File
from app.models.payments import Invoice, PaymentAttempt, Publication
from app.models.users import User, UserRole
from app.schemas.payments import PaymentInput, Publish, Verify
from app.schemas.reviews import Feedback
from app.services.assignments import claim
from app.services.payments import submit_payment, verify
from app.services.publishing import publish
from app.services.reviews import save_review


def approved(db):
    article, reviewers = setup_article(db)
    a = claim(db, article.id, reviewers[0], article.lock_version)
    save_review(
        db,
        a.id,
        reviewers[0],
        Feedback(
            decision="APPROVE",
            comments="Accepted",
            checklist={"format": True},
            required_changes_resolved=True,
        ),
    )
    final = File(
        owner_user_id=article.author_id,
        article_id=article.id,
        kind="MANUSCRIPT",
        storage_key=uuid.uuid4().hex,
        sha256="a" * 64,
        size_bytes=100,
        content_type="application/pdf",
        scan_status="CLEAN",
    )
    proof = File(
        owner_user_id=article.author_id,
        article_id=article.id,
        kind="PROOF",
        storage_key=uuid.uuid4().hex,
        sha256="b" * 64,
        size_bytes=100,
        content_type="image/png",
        scan_status="CLEAN",
    )
    admin = User(
        email="admin@example.com",
        display_name="Admin",
        password_hash="unused",
        email_verified_at=db_now(db),
    )
    db.add_all([final, proof, admin])
    db.flush()
    db.add(UserRole(user_id=admin.id, role="ADMIN"))
    db.get(ArticleVersion, article.current_version_id).manuscript_file_id = final.id
    db.commit()
    return article, db.scalar(select(Invoice)), proof, final, admin


def test_proof_does_not_publish_and_verification_is_separate(pg):
    article, invoice, proof, final, admin = approved(pg)
    author = pg.get(User, article.author_id)
    attempt = submit_payment(
        pg,
        invoice.id,
        author,
        PaymentInput(
            amount_minor=250000,
            reference="UTR12345",
            paid_at=db_now(pg) - timedelta(minutes=1),
            proof_file_id=proof.id,
        ),
    )
    pg.commit()
    assert article.status == "PAID"
    assert invoice.status == "OPEN"
    assert attempt.status == "SUBMITTED"
    verify(
        pg,
        attempt.id,
        admin,
        Verify(
            reference="UTR12345",
            receipt_note="Confirmed in test bank records",
            receipt_confirmed=True,
        ),
    )
    pg.commit()
    assert invoice.status == "PAID"
    assert article.status == "PAYMENT_APPROVED"
    pub = publish(
        pg,
        article.id,
        admin,
        Publish(
            approved_version_id=article.approved_version_id,
            final_file_id=final.id,
            slug="test-article",
            title="Test article",
            public_authors=["Author"],
        ),
    )
    pg.commit()
    assert article.status == "PUBLISH"
    assert pub.version_id == invoice.approved_version_id


def test_failed_combined_transaction_rolls_back_verification(pg):
    article, invoice, proof, final, admin = approved(pg)
    author = pg.get(User, article.author_id)
    attempt = submit_payment(
        pg,
        invoice.id,
        author,
        PaymentInput(
            amount_minor=250000, reference="UTR789", paid_at=db_now(pg), proof_file_id=proof.id
        ),
    )
    pg.commit()
    verify(
        pg,
        attempt.id,
        admin,
        Verify(reference="UTR789", receipt_note="Confirmed test receipt", receipt_confirmed=True),
    )
    with pytest.raises(HTTPException):
        publish(
            pg,
            article.id,
            admin,
            Publish(
                approved_version_id=uuid.uuid4(),
                final_file_id=final.id,
                slug="bad-version",
                title="Test",
                public_authors=["Author"],
            ),
        )
    pg.rollback()
    pg.refresh(invoice)
    pg.refresh(attempt)
    assert invoice.status == "OPEN"
    assert attempt.status == "SUBMITTED"
    assert not pg.scalar(select(Publication))


def test_multi_role_author_cannot_verify_own_payment(pg):
    article, invoice, proof, final, admin = approved(pg)
    author = pg.get(User, article.author_id)
    pg.add(UserRole(user_id=author.id, role="ADMIN"))
    pg.commit()
    attempt = submit_payment(
        pg,
        invoice.id,
        author,
        PaymentInput(
            amount_minor=250000, reference="UTR777", paid_at=db_now(pg), proof_file_id=proof.id
        ),
    )
    pg.commit()
    with pytest.raises(HTTPException) as error:
        verify(
            pg,
            attempt.id,
            author,
            Verify(reference="UTR777", receipt_note="Test receipt", receipt_confirmed=True),
        )
    assert error.value.status_code == 403
    pg.rollback()
    assert pg.get(PaymentAttempt, attempt.id).status == "SUBMITTED"


def test_rejected_payment_returns_to_approved_for_corrected_proof(pg):
    from app.services.payments import reject

    article, invoice, proof, final, admin = approved(pg)
    author = pg.get(User, article.author_id)
    attempt = submit_payment(
        pg,
        invoice.id,
        author,
        PaymentInput(
            amount_minor=invoice.amount_minor,
            reference="WRONG123",
            paid_at=db_now(pg),
            proof_file_id=proof.id,
        ),
    )
    assert article.status == "PAID"
    reject(pg, attempt.id, admin, "Receipt not found in bank records")
    pg.commit()
    assert article.status == "APPROVED"
    assert attempt.status == "REJECTED"
    assert invoice.status == "OPEN"
    corrected = submit_payment(
        pg,
        invoice.id,
        author,
        PaymentInput(
            amount_minor=invoice.amount_minor,
            reference="CORRECT123",
            paid_at=db_now(pg),
            proof_file_id=proof.id,
        ),
    )
    pg.commit()
    assert corrected.id != attempt.id
    assert article.status == "PAID"
