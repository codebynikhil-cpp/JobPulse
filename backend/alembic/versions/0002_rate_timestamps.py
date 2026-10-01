"""Timestamp mutable failed-attempt counters."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("created_at", "updated_at"):
        op.add_column(
            "auth_rate_limits",
            sa.Column(
                name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
            ),
        )


def downgrade() -> None:
    op.drop_column("auth_rate_limits", "updated_at")
    op.drop_column("auth_rate_limits", "created_at")
