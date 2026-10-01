"""Monitoring subscriptions, run records, recovery work and current match state."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(n, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        for n in ("created_at", "updated_at")
    ]


def fk(name, target, *, primary=False):
    return sa.Column(
        name,
        sa.Uuid(),
        sa.ForeignKey(target, ondelete="CASCADE"),
        primary_key=primary,
        nullable=False,
    )


def upgrade():
    op.create_table(
        "profile_companies",
        fk("profile_id", "profiles.id", primary=True),
        fk("company_id", "companies.id", primary=True),
        *timestamps(),
    )
    op.create_index("ix_profile_companies_company_id", "profile_companies", ["company_id"])
    op.create_table(
        "monitor_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        fk("source_id", "job_sources.id"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('running','success','partial','failed','anomaly','unsupported','disabled','not_due','abandoned')",
            name="ck_monitor_runs_status",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at", name="ck_monitor_runs_times"
        ),
    )
    op.create_index("ix_monitor_runs_source_started", "monitor_runs", ["source_id", "started_at"])
    op.create_table(
        "source_monitor_state",
        fk("source_id", "job_sources.id", primary=True),
        sa.Column("last_clean_count", sa.Integer()),
        *timestamps(),
        sa.CheckConstraint(
            "last_clean_count IS NULL OR last_clean_count >= 0", name="ck_source_monitor_count"
        ),
    )
    op.create_table(
        "job_monitor_state",
        fk("job_id", "jobs.id", primary=True),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("pending", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("missing_count >= 0", name="ck_job_monitor_missing"),
    )
    op.create_index("ix_job_monitor_pending", "job_monitor_state", ["pending", "job_id"])
    op.create_table(
        "job_matches",
        fk("profile_id", "profiles.id", primary=True),
        fk("job_id", "jobs.id", primary=True),
        sa.Column("matched", sa.Boolean()),
        sa.Column("score", sa.Integer()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        sa.Column("matcher_identity", sa.String(100), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="ck_job_matches_score"),
        sa.CheckConstraint("status IN ('evaluated','error')", name="ck_job_matches_status"),
        sa.CheckConstraint(
            "(status = 'evaluated' AND matched IS NOT NULL AND score IS NOT NULL) OR (status = 'error' AND matched IS NULL AND score IS NULL)",
            name="ck_job_matches_state",
        ),
    )
    op.create_index("ix_job_matches_job_id", "job_matches", ["job_id"])


def downgrade():
    for table in (
        "job_matches",
        "job_monitor_state",
        "source_monitor_state",
        "monitor_runs",
        "profile_companies",
    ):
        op.drop_table(table)
