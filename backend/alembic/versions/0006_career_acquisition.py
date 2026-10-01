"""Official company career sources: acquisition is independent of platform."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("job_sources", sa.Column("career_url", sa.String(2048)))
    op.add_column(
        "job_sources",
        sa.Column("acquisition_method", sa.String(16), nullable=False, server_default="http"),
    )
    op.add_column("job_sources", sa.Column("adapter_key", sa.String(64)))
    op.create_check_constraint(
        "ck_job_sources_acquisition", "job_sources", "acquisition_method IN ('http','browser')"
    )
    op.create_check_constraint(
        "ck_job_sources_browser_url",
        "job_sources",
        "acquisition_method != 'browser' OR career_url IS NOT NULL",
    )


def downgrade():
    op.drop_constraint("ck_job_sources_browser_url", "job_sources")
    op.drop_constraint("ck_job_sources_acquisition", "job_sources")
    for name in ("adapter_key", "acquisition_method", "career_url"):
        op.drop_column("job_sources", name)
