import uuid
from contextlib import contextmanager
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker


@contextmanager
def source_lock(factory: sessionmaker[Session], source_id: uuid.UUID):
    # Dedicated physical connection: session locks survive commit/rollback.
    key = int.from_bytes(sha256(b"jobpulse-source:" + source_id.bytes).digest()[:8], signed=True)
    with factory() as db:
        bind = db.get_bind()
    with bind.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        acquired = conn.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                except Exception:
                    # Never put a connection with a possibly held session lock back in pool.
                    conn.invalidate()
                    raise
