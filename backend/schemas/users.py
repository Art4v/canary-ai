"""
Pydantic schemas for the ``users`` table.

UserCreate validates POST bodies; UserUpdate validates PUT bodies
where every field is optional (partial update).
"""

from pydantic import BaseModel, field_validator
from typing import Optional


class UserCreate(BaseModel):
    """Schema for creating a new user row."""

    username: str          # unique display name / login handle
    email: str             # contact email
    password_hash: str     # pre-hashed password (hashing is caller's job)

    # Strip leading/trailing whitespace from all string fields.
    @field_validator("username", "email", "password_hash", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove surrounding whitespace so accidental spaces don't cause mismatches."""
        if isinstance(v, str):
            return v.strip()
        return v


class UserUpdate(BaseModel):
    """Schema for updating an existing user — all fields optional."""

    username: Optional[str] = None
    email: Optional[str] = None
    password_hash: Optional[str] = None

    @field_validator("username", "email", "password_hash", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        """Remove surrounding whitespace when a value is provided."""
        if isinstance(v, str):
            return v.strip()
        return v
