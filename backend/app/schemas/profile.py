import unicodedata
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EmploymentType = Literal["full_time", "part_time", "contract", "internship", "temporary"]
WorkMode = Literal["remote", "hybrid", "onsite"]
Experience = Annotated[Decimal, Field(ge=0, le=60, max_digits=3, decimal_places=1)]


def clean(value: str) -> str:
    if chr(0) in value:
        raise ValueError("Null characters are not allowed")
    return " ".join(unicodedata.normalize("NFKC", value).split())


def key(value: str) -> str:
    return clean(value).casefold()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Role(StrictModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name", mode="before")
    @classmethod
    def normalize(cls, value: str) -> str:
        return clean(value) if isinstance(value, str) else value


class Skill(Role):
    kind: Literal["required", "preferred"]


class Location(Role):
    excluded: bool = False


class Exclusion(StrictModel):
    term: str = Field(min_length=1, max_length=120)
    kind: Literal["keyword", "role"] = "keyword"

    @field_validator("term", mode="before")
    @classmethod
    def normalize(cls, value: str) -> str:
        return clean(value) if isinstance(value, str) else value


class ProfileCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    active: bool = False
    exp_min: Experience | None = None
    exp_max: Experience | None = None
    employment_types: list[EmploymentType] = Field(default_factory=list, max_length=5)
    work_modes: list[WorkMode] = Field(default_factory=list, max_length=3)
    roles: list[Role] = Field(default_factory=list, max_length=50)
    skills: list[Skill] = Field(default_factory=list, max_length=50)
    locations: list[Location] = Field(default_factory=list, max_length=50)
    exclusions: list[Exclusion] = Field(default_factory=list, max_length=50)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return clean(value) if isinstance(value, str) else value

    @field_validator("description")
    @classmethod
    def valid_description(cls, value: str) -> str:
        if chr(0) in value:
            raise ValueError("Null characters are not allowed")
        return value

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if self.exp_min is not None and self.exp_max is not None and self.exp_min > self.exp_max:
            raise ValueError("Minimum experience must not exceed maximum experience")
        for field in ("roles", "skills", "locations", "exclusions"):
            values = [
                key(item.term if isinstance(item, Exclusion) else item.name)
                for item in getattr(self, field)
            ]
            if len(set(values)) != len(values):
                raise ValueError(
                    f"Duplicate {field}; a skill cannot be both required and preferred"
                )
        for field in ("employment_types", "work_modes"):
            values = getattr(self, field)
            if len(set(values)) != len(values):
                raise ValueError(f"Duplicate {field}")
        excluded = {key(item.term) for item in self.exclusions}
        if any(key(role.name) in excluded for role in self.roles):
            raise ValueError("A selected role cannot also be an excluded term")
        if self.active and not self.roles:
            raise ValueError("Add at least one role before activating this profile")
        return self


class ProfilePatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    active: bool | None = None
    exp_min: Experience | None = None
    exp_max: Experience | None = None
    employment_types: list[EmploymentType] | None = Field(default=None, max_length=5)
    work_modes: list[WorkMode] | None = Field(default=None, max_length=3)
    roles: list[Role] | None = Field(default=None, max_length=50)
    skills: list[Skill] | None = Field(default=None, max_length=50)
    locations: list[Location] | None = Field(default=None, max_length=50)
    exclusions: list[Exclusion] | None = Field(default=None, max_length=50)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return clean(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def nulls(self) -> Self:
        for name in self.model_fields_set - {"exp_min", "exp_max"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null; use [] to clear a list")
        return self


class ProfileOut(ProfileCreate):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
