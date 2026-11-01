"""Align article visibility and review/payment lifecycle statuses."""

import sqlalchemy as sa
from alembic import op

revision = "0008_article_workflow"
down_revision = "0007_article_deletion"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(op.f("ck_articles_status"), "articles", type_="check")
    op.execute("UPDATE articles SET status = 'ASSIGNED' WHERE status = 'IN_REVIEW'")
    op.execute("UPDATE articles SET status = 'REJECTED' WHERE status = 'REVIEWED'")
    op.execute(
        "UPDATE review_assignments SET state = 'ACTIVE', started_at = COALESCE(started_at, assigned_at) WHERE state = 'RESERVED'"
    )
    op.execute(
        "UPDATE review_assignments SET duration_hours = 120, due_at = assigned_at + interval '120 hours' WHERE state = 'ACTIVE'"
    )
    op.execute(
        "UPDATE articles SET status = 'ASSIGNED' WHERE status = 'SUBMITTED' AND EXISTS (SELECT 1 FROM review_assignments a WHERE a.article_id = articles.id AND a.state = 'ACTIVE')"
    )
    op.execute(
        "UPDATE articles SET status = 'PAYMENT_APPROVED' WHERE status = 'APPROVED' AND EXISTS (SELECT 1 FROM invoices i WHERE i.article_id = articles.id AND i.status = 'PAID')"
    )
    op.execute(
        "UPDATE articles SET status = 'PAID' WHERE status = 'APPROVED' AND EXISTS (SELECT 1 FROM invoices i JOIN payment_attempts p ON p.invoice_id = i.id WHERE i.article_id = articles.id AND p.status = 'SUBMITTED')"
    )
    for column in ("old_status", "new_status"):
        op.execute(
            sa.text(
                f"UPDATE article_status_history SET {column} = CASE {column} WHEN 'IN_REVIEW' THEN 'ASSIGNED' WHEN 'REVIEWED' THEN 'REJECTED' ELSE {column} END"
            )
        )
    op.execute(
        sa.text(
            "UPDATE settings_versions SET \"values\" = jsonb_set(\"values\", '{review_duration_hours}', '120'::jsonb)"
        )
    )
    op.create_check_constraint(
        op.f("ck_articles_status"),
        "articles",
        "status IN ('DRAFT','SUBMITTED','ASSIGNED','REJECTED','APPROVED','PAID','PAYMENT_APPROVED','PUBLISH','DELETED')",
    )


def downgrade():
    op.drop_constraint(op.f("ck_articles_status"), "articles", type_="check")
    op.execute(
        "UPDATE articles SET status = CASE status WHEN 'ASSIGNED' THEN 'IN_REVIEW' WHEN 'REJECTED' THEN 'REVIEWED' WHEN 'PAID' THEN 'APPROVED' WHEN 'PAYMENT_APPROVED' THEN 'APPROVED' ELSE status END"
    )
    for column in ("old_status", "new_status"):
        op.execute(
            sa.text(
                f"UPDATE article_status_history SET {column} = CASE {column} WHEN 'ASSIGNED' THEN 'IN_REVIEW' WHEN 'REJECTED' THEN 'REVIEWED' WHEN 'PAID' THEN 'APPROVED' WHEN 'PAYMENT_APPROVED' THEN 'APPROVED' ELSE {column} END"
            )
        )
    op.create_check_constraint(
        op.f("ck_articles_status"),
        "articles",
        "status IN ('DRAFT','SUBMITTED','IN_REVIEW','REVIEWED','APPROVED','PUBLISH','DELETED')",
    )
