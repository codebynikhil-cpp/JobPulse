"""User job interactions and notification read state.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_job_interactions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "job_id", name="uq_user_job_interactions"),
        sa.CheckConstraint(
            "status IN ('saved', 'applied', 'ignored')",
            name="ck_user_job_interactions_status",
        ),
    )
    op.create_index(
        "ix_user_job_interactions_user_status",
        "user_job_interactions",
        ["user_id", "status"],
    )

    op.add_column(
        "notifications",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notifications_user_read",
        "notifications",
        ["user_id", "read_at"],
    )


def downgrade():
    op.drop_index("ix_notifications_user_read", "notifications")
    op.drop_column("notifications", "read_at")
    op.drop_index("ix_user_job_interactions_user_status", "user_job_interactions")
    op.drop_table("user_job_interactions")
