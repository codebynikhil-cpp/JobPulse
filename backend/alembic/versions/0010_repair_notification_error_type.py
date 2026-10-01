"""Align inherited notification error column with the Phase 7 Text contract."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("notifications", "last_error", type_=sa.Text(), existing_nullable=True)


def downgrade():
    # Phase 7 already declares Text; retain that contract rather than truncate data.
    pass
