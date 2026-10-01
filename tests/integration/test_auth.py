import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import AuthRateLimit, AuthSession, User
from app.services.auth import digest

GOOD = {"email": "Person@example.com", "password": "a strong password 123"}


def signup(client, email=None):
    return client.post("/api/auth/signup", json={**GOOD, **({"email": email} if email else {})})


def test_signup(client, migrated_database):
    response = signup(client)
    assert response.status_code == 201
    assert response.json()["email"] == "person@example.com"
    assert "password" not in response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    with Session(migrated_database) as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        session = db.scalar(select(AuthSession))
        token = client.cookies.get(settings.cookie_name)
        assert len(token) == 43
        assert session.token_hash == digest(token)
        assert session.token_hash != token


def test_login_rotates_session_and_logout_revokes(client):
    signup(client)
    old = client.cookies.get(settings.cookie_name)
    response = client.post("/api/auth/login", json=GOOD)
    assert response.status_code == 200
    assert old != client.cookies.get(settings.cookie_name)
    assert (
        client.get("/api/auth/me", headers={"Cookie": f"{settings.cookie_name}={old}"}).status_code
        == 401
    )
    assert client.get("/api/auth/me").status_code == 200
    token = client.cookies.get(settings.cookie_name)
    assert client.post("/api/auth/logout").status_code == 204
    assert (
        client.get(
            "/api/auth/me", headers={"Cookie": f"{settings.cookie_name}={token}"}
        ).status_code
        == 401
    )


def test_wrong_password_and_unknown_email_generic(client):
    signup(client)
    wrong = client.post("/api/auth/login", json={**GOOD, "password": "incorrect password"})
    from app.services import auth

    with patch.object(auth, "hasher", wraps=auth.hasher) as spy:
        unknown = client.post("/api/auth/login", json={**GOOD, "email": "nobody@example.com"})
        assert spy.verify.call_args.args[0] == auth.DUMMY_HASH
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


def test_duplicate_normalized_email(client):
    assert (
        signup(
            client,
            "  "
            + "".join(chr(ord(c) + 0xFEE0) if c.isalpha() else c for c in "PERSON@EXAMPLE.COM")
            + "  ",
        ).status_code
        == 201
    )
    assert signup(client).status_code == 409


def test_protected_access(client):
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.get("/api/auth/me", headers={"Cookie": f"{settings.cookie_name}=fake"}).status_code
        == 401
    )
    signup(client)
    assert client.get("/api/auth/me").json()["email"] == "person@example.com"


def test_password_bounds(client):
    for password in ["short", "a" * 129]:
        assert (
            client.post("/api/auth/signup", json={**GOOD, "password": password}).status_code == 422
        )
    assert client.post("/api/auth/signup", json={**GOOD, "password": "a" * 128}).status_code == 201


def test_rate_limits_failed_login_by_email_and_ignores_forwarded_header(client):
    for i in range(settings.auth_failure_limit):
        assert (
            client.post(
                "/api/auth/login", json=GOOD, headers={"X-Forwarded-For": f"192.0.2.{i}"}
            ).status_code
            == 401
        )
    assert client.post("/api/auth/login", json=GOOD).status_code == 429
    assert (
        client.post("/api/auth/login", json={**GOOD, "email": "other@example.com"}).status_code
        == 401
    )


def test_forwarded_header_requires_opt_in(client, monkeypatch):
    monkeypatch.setattr(settings, "trust_forwarded_for", True)
    for _ in range(settings.auth_failure_limit):
        assert (
            client.post(
                "/api/auth/login", json=GOOD, headers={"X-Forwarded-For": "192.0.2.1"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json=GOOD, headers={"X-Forwarded-For": "192.0.2.1"}
        ).status_code
        == 429
    )
    assert (
        client.post(
            "/api/auth/login", json=GOOD, headers={"X-Forwarded-For": "192.0.2.2"}
        ).status_code
        == 401
    )


def test_successful_attempts_not_counted(client, migrated_database):
    signup(client)
    for _ in range(settings.auth_failure_limit + 1):
        assert client.post("/api/auth/login", json=GOOD).status_code == 200
    with Session(migrated_database) as db:
        assert db.scalar(select(AuthRateLimit)) is None


def test_duplicate_signup_throttled(client):
    signup(client)
    for _ in range(settings.auth_failure_limit):
        assert signup(client).status_code == 409
    assert signup(client).status_code == 429


def test_origin_protection(client):
    assert (
        client.post(
            "/api/auth/signup", json=GOOD, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    signup(client)
    assert (
        client.post("/api/auth/logout", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert client.get("/api/auth/me").status_code == 200


def test_expired_session_and_opportunistic_cleanup(client, migrated_database):
    signup(client)
    with Session(migrated_database) as db:
        session = db.scalar(select(AuthSession))
        session.expires_at = datetime.now(UTC) - timedelta(days=1)
        expired_hash = session.token_hash
        db.add(
            AuthRateLimit(
                id=uuid.uuid4(),
                key="expired",
                route="login",
                window_start=datetime.now(UTC) - timedelta(days=1),
                attempts=2,
            )
        )
        db.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json=GOOD).status_code == 200
    with Session(migrated_database) as db:
        assert db.scalar(select(AuthSession).where(AuthSession.token_hash == expired_hash)) is None
        assert db.scalar(select(AuthRateLimit).where(AuthRateLimit.key == "expired")) is None


def test_secure_host_cookie(client, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    response = signup(client)
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-jobpulse_session=")
    assert "Secure" in cookie and "Path=/" in cookie and "Domain=" not in cookie


def test_migration_from_empty_database(migrated_database):
    inspector = inspect(migrated_database)
    assert set(inspector.get_table_names()) == {
        "users",
        "auth_sessions",
        "auth_rate_limits",
        "alembic_version",
    }
    assert inspector.get_unique_constraints("users")[0]["column_names"] == ["email"]
    assert inspector.get_foreign_keys("auth_sessions")[0]["referred_table"] == "users"


def test_parallel_failed_attempts_do_not_bypass_limit(client):
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    from app.main import app

    def attempt(_):
        with TestClient(app, headers={"Origin": settings.app_origin}) as c:
            return c.post("/api/auth/login", json=GOOD).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(attempt, range(settings.auth_failure_limit + 3)))
    assert statuses.count(401) == settings.auth_failure_limit
    assert statuses.count(429) == 3


def test_sessions_resolve_only_their_own_user(client):
    signup(client)
    first = client.cookies.get(settings.cookie_name)
    assert signup(client, "second@example.com").status_code == 201
    assert client.get("/api/auth/me").json()["email"] == "second@example.com"
    # The browser's previous session was rotated on signup as well.
    assert (
        client.get(
            "/api/auth/me", headers={"Cookie": f"{settings.cookie_name}={first}"}
        ).status_code
        == 401
    )
