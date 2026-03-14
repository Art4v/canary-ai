"""
Pydantic schemas for the ``portfolios`` table.

The create schema requires a ``username`` string which the CRUD layer
resolves to a ``user_id`` FK before inserting.
"""

from pydantic import BaseModel, field_validator
from typing import Optional


class PortfolioCreate(BaseModel):
    """Schema for creating a new portfolio row."""

    username: str                          # resolved to user_id by CRUD
    cash_reserve: float                    # uninvested cash
    total_capital_invested: float          # total capital put into holdings
    current_portfolio_value: float         # latest mark-to-market value

    @field_validator("username", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove surrounding whitespace from the username."""
        if isinstance(v, str):
            return v.strip()
        return v


class PortfolioUpdate(BaseModel):
    """Schema for updating an existing portfolio — all fields optional."""

    cash_reserve: Optional[float] = None
    total_capital_invested: Optional[float] = None
    current_portfolio_value: Optional[float] = None
