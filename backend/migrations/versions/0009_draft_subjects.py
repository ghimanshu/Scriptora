"""Allow subject selection after an initial private draft is saved."""

import sqlalchemy as sa
from alembic import op

revision = "0009_draft_subjects"
down_revision = "0008_article_workflow"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("articles", "primary_subject_id", existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint(
        op.f("ck_articles_submitted_subject"),
        "articles",
        "status IN ('DRAFT','DELETED') OR primary_subject_id IS NOT NULL",
    )
    op.execute(
        "INSERT INTO article_subjects (article_id, subject_id) SELECT id, primary_subject_id FROM articles WHERE primary_subject_id IS NOT NULL ON CONFLICT DO NOTHING"
    )


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM articles WHERE primary_subject_id IS NULL)"))
        .scalar()
    ):
        raise RuntimeError("Select a subject for subjectless drafts before downgrading.")
    op.drop_constraint(op.f("ck_articles_submitted_subject"), "articles", type_="check")
    op.alter_column("articles", "primary_subject_id", existing_type=sa.Uuid(), nullable=False)
