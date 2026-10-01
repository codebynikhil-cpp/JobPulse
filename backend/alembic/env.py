from alembic import context

from app.db.session import Base, engine
from app.models import (  # noqa: F401
    auth,
    catalog,
    job,
    job_interaction,
    monitoring,
    notification,
    profile,
)

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
