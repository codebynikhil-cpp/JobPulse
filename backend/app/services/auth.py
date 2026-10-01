import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal, NoReturn

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import AuthRateLimit, AuthSession, User
from app.schemas.auth import Credentials

AuthRoute = Literal["signup", "login"]
RateContext = tuple[str, datetime]

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def rate_context(db: Session, ip: str, email: str, route: AuthRoute) -> RateContext:
    now = datetime.now(UTC)
    window = settings.auth_window_seconds
    start = datetime.fromtimestamp(int(now.timestamp()) // window * window, UTC)
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    db.execute(delete(AuthRateLimit).where(AuthRateLimit.window_start < start))
    db.commit()
    key = digest(ip + "\0" + email)
    # Serialize attempts for this identity across processes, including first insert.
    lock = int(key[:16], 16)
    if lock >= 2**63:
        lock -= 2**64
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    row = db.scalar(
        select(AuthRateLimit).where(
            AuthRateLimit.key == key,
            AuthRateLimit.route == route,
            AuthRateLimit.window_start == start,
        )
    )
    if row and row.attempts >= settings.auth_failure_limit:
        db.commit()
        raise HTTPException(
            429, "Too many failed attempts; try again later", headers={"Retry-After": str(window)}
        )
    return key, start


def fail(
    db: Session, context: RateContext, route: AuthRoute, status: int, message: str
) -> NoReturn:
    key, start = context
    statement = insert(AuthRateLimit).values(key=key, route=route, window_start=start, attempts=1)
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["key", "route", "window_start"],
            set_={"attempts": AuthRateLimit.attempts + 1, "updated_at": func.now()},
        )
    )
    db.commit()
    raise HTTPException(status, message)


def authenticate(
    db: Session, credentials: Credentials, ip: str, route: AuthRoute, old_token: str | None
) -> tuple[User, str]:
    context = rate_context(db, ip, credentials.email, route)
    user = db.scalar(select(User).where(User.email == credentials.email))
    if route == "signup":
        if user:
            fail(db, context, route, 409, "Email already registered")
        user = User(email=credentials.email, password_hash=hasher.hash(credentials.password))
        db.add(user)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            if getattr(exc.orig, "sqlstate", None) != "23505":
                raise
            fail(db, context, route, 409, "Email already registered")
    else:
        try:
            valid = hasher.verify(user.password_hash if user else DUMMY_HASH, credentials.password)
        except VerificationError:
            valid = False
        if not user or not valid:
            fail(db, context, route, 401, "Invalid email or password")
    if old_token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(old_token)))
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=digest(token),
            expires_at=datetime.now(UTC) + timedelta(hours=settings.session_hours),
        )
    )
    db.commit()
    return user, token


def current_user(db: Session, token: str | None) -> User:
    if not token:
        raise HTTPException(401, "Authentication required")
    user = db.scalar(
        select(User)
        .join(AuthSession)
        .where(
            AuthSession.token_hash == digest(token),
            AuthSession.expires_at > datetime.now(UTC),
        )
    )
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


def logout(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(token)))
        db.commit()
