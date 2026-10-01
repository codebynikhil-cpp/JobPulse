"""Company, source classification and canonical job persistence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_companies_name"),
        sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_companies_slug"),
    )
    op.create_table(
        "job_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("poll_interval_sec", sa.Integer(), nullable=False),
        *[
            sa.Column(name, sa.DateTime(timezone=True))
            for name in ("last_checked_at", "last_success_at", "last_error_at")
        ],
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("health_status", sa.String(16), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("id", "company_id", name="uq_job_sources_identity_company"),
        sa.CheckConstraint(
            "source_type IN ('greenhouse','lever','ashby','workday','api','custom')",
            name="ck_job_sources_source_type",
        ),
        sa.CheckConstraint("poll_interval_sec >= 60", name="ck_job_sources_poll_interval"),
        sa.CheckConstraint("consecutive_failures >= 0", name="ck_job_sources_failures"),
        sa.CheckConstraint(
            "health_status IN ('unknown','healthy','degraded','failing','unsupported')",
            name="ck_job_sources_health",
        ),
        sa.CheckConstraint("jsonb_typeof(config) = 'object'", name="ck_job_sources_config"),
    )
    op.create_index("ix_job_sources_company_id", "job_sources", ["company_id"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("external_job_id", sa.String(512), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(300), nullable=False),
        sa.Column("employment_type", sa.String(24)),
        sa.Column("experience_text", sa.Text()),
        sa.Column("min_exp_years", sa.Numeric(4, 1)),
        sa.Column("max_exp_years", sa.Numeric(4, 1)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("application_url", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("raw_data", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("source_id", "external_job_id", name="uq_jobs_source_external_id"),
        sa.ForeignKeyConstraint(
            ["source_id", "company_id"],
            ["job_sources.id", "job_sources.company_id"],
            ondelete="RESTRICT",
            name="fk_jobs_source_company",
        ),
        sa.CheckConstraint("length(trim(external_job_id)) > 0", name="ck_jobs_external_id"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_jobs_title"),
        sa.CheckConstraint(
            "employment_type IS NULL OR employment_type IN ('full_time','part_time','contract','internship','temporary')",
            name="ck_jobs_employment_type",
        ),
        sa.CheckConstraint(
            "min_exp_years IS NULL OR min_exp_years BETWEEN 0 AND 100", name="ck_jobs_min_exp"
        ),
        sa.CheckConstraint(
            "max_exp_years IS NULL OR max_exp_years BETWEEN 0 AND 100", name="ck_jobs_max_exp"
        ),
        sa.CheckConstraint(
            "min_exp_years IS NULL OR max_exp_years IS NULL OR min_exp_years <= max_exp_years",
            name="ck_jobs_exp_range",
        ),
        sa.CheckConstraint("last_seen_at >= first_seen_at", name="ck_jobs_seen_range"),
        sa.CheckConstraint(
            "(status = 'open' AND closed_at IS NULL) OR (status = 'closed' AND closed_at >= last_seen_at)",
            name="ck_jobs_status_closed",
        ),
        sa.CheckConstraint(
            "status != 'closed' OR closed_at IS NOT NULL", name="ck_jobs_closed_required"
        ),
        sa.CheckConstraint(
            "content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'", name="ck_jobs_content_hash"
        ),
        sa.CheckConstraint("jsonb_typeof(raw_data) = 'object'", name="ck_jobs_raw_data"),
    )
    for name, fields in [
        ("ix_jobs_source_id", ["source_id"]),
        ("ix_jobs_content_hash", ["content_hash"]),
        ("ix_jobs_company_closed_at", ["company_id", "closed_at"]),
        ("ix_jobs_first_seen_at", ["first_seen_at"]),
    ]:
        op.create_index(name, "jobs", fields)


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("job_sources")
    op.drop_table("companies")
