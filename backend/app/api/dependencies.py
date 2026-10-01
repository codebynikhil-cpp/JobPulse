from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.auth import User
from app.services.auth import current_user

DB = Annotated[Session, Depends(get_db)]


def authenticated_user(request: Request, db: DB) -> User:
    return current_user(db, request.cookies.get(settings.cookie_name))


CurrentUser = Annotated[User, Depends(authenticated_user)]
