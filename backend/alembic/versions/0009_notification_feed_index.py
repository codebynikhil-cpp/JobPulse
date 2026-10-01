"""Owner-scoped notification feed index; compatible with existing 0008 installs."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_notifications_user_created", "notifications", ["user_id", "created_at", "id"]
    )


def downgrade():
    op.drop_index("ix_notifications_user_created", "notifications")
