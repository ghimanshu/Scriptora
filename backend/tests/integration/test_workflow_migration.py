import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from test_workflow import setup_article

from app.db.session import db_now
from app.models.articles import File
from app.models.payments import Invoice, PaymentAttempt
from app.services.assignments import claim


@pytest.mark.parametrize("status", ["ASSIGNED", "REJECTED", "PAID", "PAYMENT_APPROVED"])
def test_existing_article_states_survive_workflow_migration(pg, pg_engine, status):
    article, reviewers = setup_article(pg)
    if status == "ASSIGNED":
        claim(pg, article.id, reviewers[0], article.lock_version)
    else:
        article.status = status
    if status in ("PAID", "PAYMENT_APPROVED"):
        article.approved_version_id = article.current_version_id
        invoice = Invoice(
            article_id=article.id,
            approved_version_id=article.current_version_id,
            invoice_number="MIGRATION",
            amount_minor=1000,
            currency="INR",
            fee_policy_version=1,
            instructions="Bank instructions",
            status="PAID" if status == "PAYMENT_APPROVED" else "OPEN",
        )
        proof = File(
            owner_user_id=article.author_id,
            article_id=article.id,
            kind="PROOF",
            storage_key="migration-proof",
            sha256="a" * 64,
            size_bytes=1,
            content_type="image/png",
            scan_status="CLEAN",
        )
        pg.add_all([invoice, proof])
        pg.flush()
        if status == "PAID":
            pg.add(
                PaymentAttempt(
                    invoice_id=invoice.id,
                    submitted_by=article.author_id,
                    reference_normalized="MIGRATION",
                    paid_at=db_now(pg),
                    amount_minor=1000,
                    proof_file_id=proof.id,
                )
            )
    pg.commit()
    article_id = article.id
    pg.close()
    config = Config("alembic.ini")
    command.downgrade(config, "0007_article_deletion")
    try:
        command.upgrade(config, "head")
        with pg_engine.connect() as connection:
            state = connection.execute(
                text("SELECT status FROM articles WHERE id=:id"), {"id": article_id}
            ).scalar_one()
            assert state == status
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0009_draft_subjects"
            )
    finally:
        command.upgrade(config, "head")
