"""Index unread notifications and backfill missing in-app copies of email events."""

import sqlalchemy as sa
from alembic import op

revision = "0010_notification_inbox"
down_revision = "0009_draft_subjects"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_notifications_recipient_created", "notifications", ["recipient_id", "created_at", "id"]
    )
    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ["recipient_id", "created_at", "id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.execute("""
        INSERT INTO notifications (id, recipient_id, event_id, type, payload, read_at, created_at, updated_at)
        SELECT gen_random_uuid(), u.id, e.id, e.type, e.payload - 'encrypted_token' - 'recipients', NULL, e.created_at, now()
        FROM outbox_events e
        CROSS JOIN LATERAL jsonb_array_elements_text(CASE WHEN jsonb_typeof(e.payload->'recipients') = 'array' THEN e.payload->'recipients' ELSE '[]'::jsonb END) recipient(value)
        JOIN users u ON u.id::text = recipient.value
        ON CONFLICT (recipient_id, event_id) DO NOTHING
    """)


def downgrade():
    op.drop_index("ix_notifications_recipient_unread", table_name="notifications")
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
