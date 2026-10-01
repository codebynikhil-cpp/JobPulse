"""User-owned profiles and normalized configuration."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_key", sa.String(400), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("exp_min", sa.Numeric(3, 1)),
        sa.Column("exp_max", sa.Numeric(3, 1)),
        sa.Column("employment_types", postgresql.ARRAY(sa.String(24)), nullable=False),
        sa.Column("work_modes", postgresql.ARRAY(sa.String(16)), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("user_id", "name_key", name="uq_profiles_owner_name"),
        sa.CheckConstraint(
            "exp_min IS NULL OR exp_min BETWEEN 0 AND 60", name="ck_profiles_exp_min"
        ),
        sa.CheckConstraint(
            "exp_max IS NULL OR exp_max BETWEEN 0 AND 60", name="ck_profiles_exp_max"
        ),
        sa.CheckConstraint(
            "exp_min IS NULL OR exp_max IS NULL OR exp_min <= exp_max", name="ck_profiles_exp_range"
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_profiles_name"),
        sa.CheckConstraint("length(description) <= 2000", name="ck_profiles_description"),
        sa.CheckConstraint(
            "employment_types <@ ARRAY['full_time','part_time','contract','internship','temporary']::varchar[]",
            name="ck_profiles_employment_types",
        ),
        sa.CheckConstraint(
            "work_modes <@ ARRAY['remote','hybrid','onsite']::varchar[]",
            name="ck_profiles_work_modes",
        ),
    )
    op.create_index("ix_profiles_owner_created", "profiles", ["user_id", "created_at", "id"])
    for table in ("profile_roles", "profile_skills", "profile_locations", "profile_exclusions"):
        is_exclusion = table == "profile_exclusions"
        value = "term" if is_exclusion else "name"
        columns = [
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "profile_id",
                sa.Uuid(),
                sa.ForeignKey("profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(value, sa.String(120), nullable=False),
            sa.Column(f"normalized_{value}", sa.String(480), nullable=False),
            *timestamps(),
            sa.UniqueConstraint("profile_id", f"normalized_{value}", name=f"uq_{table}_value"),
            sa.CheckConstraint(f"length(trim({value})) > 0", name=f"ck_{table}_{value}"),
        ]
        if table == "profile_skills":
            columns.extend(
                [
                    sa.Column("kind", sa.String(16), nullable=False),
                    sa.CheckConstraint(
                        "kind IN ('required', 'preferred')", name="ck_profile_skills_kind"
                    ),
                ]
            )
        if table == "profile_locations":
            columns.append(sa.Column("excluded", sa.Boolean(), nullable=False))
        if is_exclusion:
            columns.extend(
                [
                    sa.Column("kind", sa.String(16), nullable=False),
                    sa.CheckConstraint(
                        "kind IN ('keyword', 'role')", name="ck_profile_exclusions_kind"
                    ),
                ]
            )
        op.create_table(table, *columns)


def downgrade() -> None:
    for table in ("profile_exclusions", "profile_locations", "profile_skills", "profile_roles"):
        op.drop_table(table)
    op.drop_table("profiles")
