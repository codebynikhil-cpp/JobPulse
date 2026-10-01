import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.catalog import Company
from app.models.monitoring import ProfileCompany
from app.models.profile import Profile


def subscribe_company(
    db: Session, user_id: uuid.UUID, profile_id: uuid.UUID, company_id: uuid.UUID
) -> None:
    """Internal configuration helper: explicit owner check, caller owns commit."""
    profile = db.scalar(
        select(Profile)
        .where(Profile.id == profile_id, Profile.user_id == user_id)
        .with_for_update()
    )
    if profile is None:
        raise LookupError("Profile not found for this owner")
    if db.get(Company, company_id) is None:
        raise LookupError("Company not found")
    db.execute(
        insert(ProfileCompany)
        .values(profile_id=profile_id, company_id=company_id)
        .on_conflict_do_nothing()
    )
