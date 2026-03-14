"""
Pydantic schemas for the ``users`` table.

UserCreate validates POST bodies; UserUpdate validates PUT bodies
where every field is optional (partial update).
"""

from pydantic import BaseModel, field_validator
from typing import Optional


class UserCreate(BaseModel):
    """Schema for creating a new user row.

    Accepts a plaintext ``password`` from the client.
    The CRUD layer hashes it with bcrypt before storing as ``password_hash``
    in the database — callers never need to hash manually.
    """

    username: str          # unique display name / login handle
    email: str             # contact email
    password: str          # plaintext password — hashed server-side before DB insert

    # Strip leading/trailing whitespace from all string fields.
    @field_validator("username", "email", "password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove surrounding whitespace so accidental spaces don't cause mismatches."""
        if isinstance(v, str):
            return v.strip()
        return v


class UserLogin(BaseModel):
    """Schema for the login request body.

    Accepts an email and plaintext password — the CRUD layer
    verifies the password against the stored bcrypt hash.
    """

    email: str       # the email address used during registration
    password: str    # plaintext password to verify

    @field_validator("email", "password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove surrounding whitespace."""
        if isinstance(v, str):
            return v.strip()
        return v


class UserUpdate(BaseModel):
    """Schema for updating an existing user — all fields optional.

    If ``password`` is supplied, the CRUD layer hashes it with bcrypt
    before writing ``password_hash`` to the database.
    """

    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None  # plaintext password — hashed server-side

    @field_validator("username", "email", "password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        """Remove surrounding whitespace when a value is provided."""
        if isinstance(v, str):
            return v.strip()
        return v
