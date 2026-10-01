import os
import subprocess
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    from app.core.config import settings

    url = make_url(settings.database_url)
    name = "jobpulse_test_" + uuid.uuid4().hex
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    test_url = url.set(database=name).render_as_string(hide_password=False)
    env = dict(os.environ, DATABASE_URL=test_url)
    subprocess.run(["alembic", "upgrade", "head"], env=env, check=True)
    from sqlalchemy.orm import sessionmaker

    from app.db import session
    from app.main import app

    engine = create_engine(test_url)
    factory = sessionmaker(engine, expire_on_commit=False)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[session.get_db] = override
    yield engine
    app.dependency_overrides.clear()
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(autouse=True)
def empty_tables(migrated_database):
    with migrated_database.begin() as conn:
        conn.execute(text("TRUNCATE auth_sessions, auth_rate_limits, users, companies CASCADE"))


@pytest.fixture
def client():
    from app.core.config import settings
    from app.main import app

    with TestClient(app, headers={"Origin": settings.app_origin}) as c:
        yield c
