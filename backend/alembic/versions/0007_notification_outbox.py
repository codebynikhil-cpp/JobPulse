"""Transactional user/job notification outbox."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "job_monitor_state",
        sa.Column("event_kind", sa.String(16), nullable=False, server_default="changed"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("revision", sa.String(64), nullable=False),
        sa.Column("material_hash", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("provider_id", sa.String(128)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "user_id", "job_id", "kind", "revision", name="uq_notifications_identity"
        ),
        sa.CheckConstraint("kind IN ('new_job','changed_job')", name="ck_notifications_kind"),
        sa.CheckConstraint(
            "status IN ('pending','processing','failed','sent','permanently_failed','cancelled')",
            name="ck_notifications_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_notifications_attempts"),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_notifications_payload"),
        sa.CheckConstraint(
            "(status = 'processing') = (claim_token IS NOT NULL AND lease_until IS NOT NULL)",
            name="ck_notifications_claim",
        ),
        sa.CheckConstraint(
            "(status = 'sent') = (sent_at IS NOT NULL)", name="ck_notifications_sent"
        ),
    )
    op.create_index("ix_notifications_due", "notifications", ["status", "available_at", "id"])


def downgrade():
    op.drop_table("notifications")
    op.drop_column("job_monitor_state", "event_kind")
