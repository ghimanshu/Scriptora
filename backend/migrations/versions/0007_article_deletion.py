"""Allow audited article deletion without destroying linked records."""

from alembic import op

revision = "0007_article_deletion"
down_revision = "0006_reviewer_decisions"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(op.f("ck_articles_status"), "articles", type_="check")
    op.create_check_constraint(
        op.f("ck_articles_status"),
        "articles",
        "status IN ('DRAFT','SUBMITTED','IN_REVIEW','REVIEWED','APPROVED','PUBLISH','DELETED')",
    )


def downgrade():
    # Refuse rollback while deleted rows exist rather than silently restoring them.
    op.drop_constraint(op.f("ck_articles_status"), "articles", type_="check")
    op.create_check_constraint(
        op.f("ck_articles_status"),
        "articles",
        "status IN ('DRAFT','SUBMITTED','IN_REVIEW','REVIEWED','APPROVED','PUBLISH')",
    )
