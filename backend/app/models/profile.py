from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Profile(Timestamps, Base):
    __tablename__ = "profiles"
    __table_args__ = (
        Index("ix_profiles_owner_created", "user_id", "created_at", "id"),
        UniqueConstraint("user_id", "name_key", name="uq_profiles_owner_name"),
        CheckConstraint("exp_min IS NULL OR exp_min BETWEEN 0 AND 60", name="ck_profiles_exp_min"),
        CheckConstraint("exp_max IS NULL OR exp_max BETWEEN 0 AND 60", name="ck_profiles_exp_max"),
        CheckConstraint(
            "exp_min IS NULL OR exp_max IS NULL OR exp_min <= exp_max", name="ck_profiles_exp_range"
        ),
        CheckConstraint("length(trim(name)) > 0", name="ck_profiles_name"),
        CheckConstraint("length(description) <= 2000", name="ck_profiles_description"),
        CheckConstraint(
            "employment_types <@ ARRAY['full_time','part_time','contract','internship','temporary']::varchar[]",
            name="ck_profiles_employment_types",
        ),
        CheckConstraint(
            "work_modes <@ ARRAY['remote','hybrid','onsite']::varchar[]",
            name="ck_profiles_work_modes",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(400))
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    exp_min: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    exp_max: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    employment_types: Mapped[list[str]] = mapped_column(ARRAY(String(24)), default=list)
    work_modes: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    roles: Mapped[list[ProfileRole]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="ProfileRole.normalized_name"
    )
    skills: Mapped[list[ProfileSkill]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="ProfileSkill.normalized_name"
    )
    locations: Mapped[list[ProfileLocation]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProfileLocation.normalized_name",
    )
    exclusions: Mapped[list[ProfileExclusion]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProfileExclusion.normalized_term",
    )


class NamedChild(Timestamps):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    normalized_name: Mapped[str] = mapped_column(String(480))


class ProfileRole(NamedChild, Base):
    __tablename__ = "profile_roles"
    __table_args__ = (
        UniqueConstraint("profile_id", "normalized_name", name="uq_profile_roles_value"),
        CheckConstraint("length(trim(name)) > 0", name="ck_profile_roles_name"),
    )


class ProfileSkill(NamedChild, Base):
    __tablename__ = "profile_skills"
    __table_args__ = (
        UniqueConstraint("profile_id", "normalized_name", name="uq_profile_skills_value"),
        CheckConstraint("kind IN ('required', 'preferred')", name="ck_profile_skills_kind"),
        CheckConstraint("length(trim(name)) > 0", name="ck_profile_skills_name"),
    )
    kind: Mapped[str] = mapped_column(String(16))


class ProfileLocation(NamedChild, Base):
    __tablename__ = "profile_locations"
    __table_args__ = (
        UniqueConstraint("profile_id", "normalized_name", name="uq_profile_locations_value"),
        CheckConstraint("length(trim(name)) > 0", name="ck_profile_locations_name"),
    )
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)


class ProfileExclusion(Timestamps, Base):
    __tablename__ = "profile_exclusions"
    __table_args__ = (
        UniqueConstraint("profile_id", "normalized_term", name="uq_profile_exclusions_value"),
        CheckConstraint("kind IN ('keyword', 'role')", name="ck_profile_exclusions_kind"),
        CheckConstraint("length(trim(term)) > 0", name="ck_profile_exclusions_term"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    term: Mapped[str] = mapped_column(String(120))
    normalized_term: Mapped[str] = mapped_column(String(480))
    kind: Mapped[str] = mapped_column(String(16))
