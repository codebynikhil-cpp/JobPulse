from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.auth import User
from app.schemas.auth import Credentials, UserOut
from app.services import auth

router = APIRouter(prefix="/api/auth")


def check_origin(request: Request) -> None:
    if request.headers.get("origin") != settings.app_origin:
        raise HTTPException(403, "Invalid request origin")


def issue(
    request: Request,
    response: Response,
    credentials: Credentials,
    db: Session,
    route: auth.AuthRoute,
) -> User:
    ip = request.client.host if request.client else "unknown"
    if settings.trust_forwarded_for and request.headers.get("x-forwarded-for"):
        ip = request.headers["x-forwarded-for"].split(",")[0].strip()
    user, token = auth.authenticate(
        db, credentials, ip, route, request.cookies.get(settings.cookie_name)
    )
    response.set_cookie(
        settings.cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.session_hours * 3600,
    )
    return user


@router.post(
    "/signup", response_model=UserOut, status_code=201, dependencies=[Depends(check_origin)]
)
def signup(
    credentials: Credentials,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    return issue(request, response, credentials, db, "signup")


@router.post("/login", response_model=UserOut, dependencies=[Depends(check_origin)])
def login(
    credentials: Credentials,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    return issue(request, response, credentials, db, "login")


@router.post("/logout", status_code=204, dependencies=[Depends(check_origin)])
def logout(request: Request, response: Response, db: Annotated[Session, Depends(get_db)]) -> None:
    auth.logout(db, request.cookies.get(settings.cookie_name))
    response.delete_cookie(
        settings.cookie_name, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )


@router.get("/me", response_model=UserOut)
def me(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    return auth.current_user(db, request.cookies.get(settings.cookie_name))
