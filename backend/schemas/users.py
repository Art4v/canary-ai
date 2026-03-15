"""
Pydantic schemas for the ``users`` table.

UserCreate validates POST bodies; UserUpdate validates PUT bodies
where every field is optional (partial update).

The ``trading_style`` field uses a string enum with three allowed values:
``balanced``, ``risk-averse``, and ``risk-aggressive``.

Server-side validation mirrors the frontend HTML5 form constraints:
  - ``required`` fields must be non-empty strings
  - ``type="email"`` fields must contain a valid email format (user@domain)
"""

import re
from pydantic import BaseModel, field_validator
from typing import Optional

# Allowed values for the trading_style column (Supabase USER-DEFINED enum).
TRADING_STYLE_VALUES = {"balanced", "risk-averse", "risk-aggressive"}

# Simple email regex matching the HTML5 <input type="email"> spec.
# Checks for non-empty local part, an @ sign, and a domain with at least one dot.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class UserCreate(BaseModel):
    """Schema for creating a new user row.

    Accepts a plaintext ``password`` from the client.
    The CRUD layer hashes it with bcrypt before storing as ``password_hash``
    in the database — callers never need to hash manually.

    Optional fields (api_key, trading_style, notifications) can be set
    at registration time or updated later via PUT.

    Validation mirrors frontend HTML5 form constraints:
      - username, email, password are required (non-empty after stripping)
      - email must match a basic email format (mirrors ``type="email"``)
    """

    username: str          # unique display name / login handle
    email: str             # contact email
    password: str          # plaintext password — hashed server-side before DB insert
    api_key: Optional[str] = None            # user's personal API key for external services
    trading_style: Optional[str] = None      # one of: balanced, risk-averse, risk-aggressive
    notifications: Optional[bool] = None     # whether the user wants notifications enabled
    memory: Optional[str] = None             # chatbot persistent session memory (free-form text)
    preferences: Optional[dict] = None       # chatbot collected investment preferences (JSONB)

    # Strip leading/trailing whitespace from all string fields.
    @field_validator("username", "email", "password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove surrounding whitespace so accidental spaces don't cause mismatches."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("username", mode="after")
    @classmethod
    def username_not_empty(cls, v: str) -> str:
        """Mirrors the HTML ``required`` attribute — username cannot be blank."""
        if not v:
            raise ValueError("Username is required")
        return v

    @field_validator("email", mode="after")
    @classmethod
    def email_valid(cls, v: str) -> str:
        """Mirrors the HTML ``required`` + ``type="email"`` attributes.

        Rejects empty strings and values that don't look like a valid email
        (local@domain.tld).
        """
        if not v:
            raise ValueError("Email is required")
        if not _EMAIL_RE.match(v):
            raise ValueError("Please enter a valid email address")
        return v

    @field_validator("password", mode="after")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        """Mirrors the HTML ``required`` attribute — password cannot be blank."""
        if not v:
            raise ValueError("Password is required")
        return v

    @field_validator("trading_style", mode="before")
    @classmethod
    def validate_trading_style(cls, v: str | None) -> str | None:
        """Ensure trading_style is one of the allowed enum values."""
        if v is not None and v not in TRADING_STYLE_VALUES:
            raise ValueError(
                f"trading_style must be one of {sorted(TRADING_STYLE_VALUES)}, got '{v}'"
            )
        return v


class UserLogin(BaseModel):
    """Schema for the login request body.

    Accepts an email and plaintext password — the CRUD layer
    verifies the password against the stored bcrypt hash.

    Validation mirrors frontend HTML5 form constraints:
      - email and password are required (non-empty after stripping)
      - email must match a basic email format (mirrors ``type="email"``)
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

    @field_validator("email", mode="after")
    @classmethod
    def email_valid(cls, v: str) -> str:
        """Mirrors the HTML ``required`` + ``type="email"`` attributes.

        Rejects empty strings and values that don't look like a valid email.
        """
        if not v:
            raise ValueError("Email is required")
        if not _EMAIL_RE.match(v):
            raise ValueError("Please enter a valid email address")
        return v

    @field_validator("password", mode="after")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        """Mirrors the HTML ``required`` attribute — password cannot be blank."""
        if not v:
            raise ValueError("Password is required")
        return v


class UserUpdate(BaseModel):
    """Schema for updating an existing user — all fields optional.

    If ``password`` is supplied, the CRUD layer hashes it with bcrypt
    before writing ``password_hash`` to the database.

    Additional optional fields: api_key, trading_style, notifications.
    """

    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None           # plaintext password — hashed server-side
    api_key: Optional[str] = None            # user's personal API key for external services
    trading_style: Optional[str] = None      # one of: balanced, risk-averse, risk-aggressive
    notifications: Optional[bool] = None     # whether the user wants notifications enabled
    memory: Optional[str] = None             # chatbot persistent session memory (free-form text)
    preferences: Optional[dict] = None       # chatbot collected investment preferences (JSONB)

    @field_validator("username", "email", "password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        """Remove surrounding whitespace when a value is provided."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("trading_style", mode="before")
    @classmethod
    def validate_trading_style(cls, v: str | None) -> str | None:
        """Ensure trading_style is one of the allowed enum values."""
        if v is not None and v not in TRADING_STYLE_VALUES:
            raise ValueError(
                f"trading_style must be one of {sorted(TRADING_STYLE_VALUES)}, got '{v}'"
            )
        return v
