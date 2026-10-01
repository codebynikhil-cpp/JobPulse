import json
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.profile import Profile, ProfileExclusion, ProfileLocation, ProfileRole, ProfileSkill
from app.schemas.profile import ProfileCreate, ProfileOut, ProfilePatch, key

RELATIONS = {
    "roles": ProfileRole,
    "skills": ProfileSkill,
    "locations": ProfileLocation,
    "exclusions": ProfileExclusion,
}


def query(user_id: uuid.UUID):
    return (
        select(Profile)
        .where(Profile.user_id == user_id)
        .options(*(selectinload(getattr(Profile, name)) for name in RELATIONS))
    )


def get(db: Session, user_id: uuid.UUID, profile_id: uuid.UUID, *, lock: bool = False) -> Profile:
    statement = query(user_id).where(Profile.id == profile_id)
    if lock:
        statement = statement.with_for_update()
    profile = db.scalar(statement)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    return profile


def list_profiles(db: Session, user_id: uuid.UUID, limit: int, offset: int) -> list[Profile]:
    return list(
        db.scalars(
            query(user_id)
            .order_by(Profile.created_at.desc(), Profile.id)
            .limit(limit)
            .offset(offset)
        )
    )


def commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(
                409, "A profile with this name or a duplicate configuration entry already exists"
            ) from exc
        raise


def apply(profile: Profile, data: ProfileCreate, supplied: set[str]) -> None:
    values = data.model_dump()
    for name in supplied - RELATIONS.keys():
        setattr(profile, name, values[name])
    if "name" in supplied:
        profile.name_key = key(data.name)
    for name in supplied & RELATIONS.keys():
        rows = []
        for item in values[name]:
            field = "term" if name == "exclusions" else "name"
            rows.append(RELATIONS[name](**item, **{f"normalized_{field}": key(item[field])}))
        setattr(profile, name, rows)


def create(db: Session, user_id: uuid.UUID, data: ProfileCreate) -> Profile:
    profile = Profile(user_id=user_id)
    apply(profile, data, set(ProfileCreate.model_fields))
    db.add(profile)
    commit(db)
    profile_id = profile.id
    db.expire(profile)
    return get(db, user_id, profile_id)


def update(db: Session, user_id: uuid.UUID, profile_id: uuid.UUID, patch: ProfilePatch) -> Profile:
    profile = get(db, user_id, profile_id, lock=True)
    current = ProfileOut.model_validate(profile).model_dump(include=set(ProfileCreate.model_fields))
    try:
        validated = ProfileCreate.model_validate(
            {**current, **patch.model_dump(exclude_unset=True)}
        )
    except ValidationError as exc:
        raise HTTPException(422, json.loads(exc.json(include_context=False))) from exc
    supplied = patch.model_fields_set
    # Flush removal before reinserting equal keys to avoid transient unique violations.
    for name in supplied & RELATIONS.keys():
        getattr(profile, name).clear()
    db.flush()
    apply(profile, validated, supplied)
    if supplied:
        profile.updated_at = datetime.now(UTC)
    commit(db)
    db.expire(profile)
    return get(db, user_id, profile_id)


def delete(db: Session, user_id: uuid.UUID, profile_id: uuid.UUID) -> None:
    db.delete(get(db, user_id, profile_id, lock=True))
    db.commit()
