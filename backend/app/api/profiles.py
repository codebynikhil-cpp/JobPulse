import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.auth import check_origin
from app.api.dependencies import DB, CurrentUser
from app.models.profile import Profile
from app.schemas.profile import ProfileCreate, ProfileOut, ProfilePatch
from app.services import profiles

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.post("", response_model=ProfileOut, status_code=201, dependencies=[Depends(check_origin)])
def create(data: ProfileCreate, db: DB, user: CurrentUser) -> Profile:
    return profiles.create(db, user.id, data)


@router.get("", response_model=list[ProfileOut])
def list_profiles(
    db: DB,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Profile]:
    return profiles.list_profiles(db, user.id, limit, offset)


@router.get("/{profile_id}", response_model=ProfileOut)
def get(profile_id: uuid.UUID, db: DB, user: CurrentUser) -> Profile:
    return profiles.get(db, user.id, profile_id)


@router.patch("/{profile_id}", response_model=ProfileOut, dependencies=[Depends(check_origin)])
def update(profile_id: uuid.UUID, data: ProfilePatch, db: DB, user: CurrentUser) -> Profile:
    return profiles.update(db, user.id, profile_id, data)


@router.delete("/{profile_id}", status_code=204, dependencies=[Depends(check_origin)])
def delete(profile_id: uuid.UUID, db: DB, user: CurrentUser) -> None:
    profiles.delete(db, user.id, profile_id)
