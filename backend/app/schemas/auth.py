import unicodedata
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def normalize_email(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().lower()


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("email", mode="after")
    @classmethod
    def canonical(cls, value: str) -> str:
        return normalize_email(value)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
