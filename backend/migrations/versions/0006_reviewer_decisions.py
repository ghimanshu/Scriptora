"""Persist reviewer rejection separately from pending approval."""

import sqlalchemy as sa
from alembic import op

revision = "0006_reviewer_decisions"
down_revision = "0005_outbox_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "reviewer_profiles",
        sa.Column("rejected", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade():
    op.drop_column("reviewer_profiles", "rejected")
