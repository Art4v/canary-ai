"""
Pydantic schemas for the ``holdings`` table.

The create schema requires ``username`` (resolved to portfolio_id
through users -> portfolios) and the holding details.
"""

from pydantic import BaseModel, field_validator
from typing import Optional


class HoldingCreate(BaseModel):
    """Schema for creating a new holding row."""

    username: str              # resolved to portfolio_id via user -> portfolio chain
    ticker: str                # stock ticker symbol (e.g. "AAPL")
    quantity: float            # number of shares held
    average_buy_price: float   # average cost basis per share

    @field_validator("username", "ticker", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove surrounding whitespace from string fields."""
        if isinstance(v, str):
            return v.strip()
        return v


class HoldingUpdate(BaseModel):
    """Schema for updating an existing holding — all fields optional."""

    ticker: Optional[str] = None
    quantity: Optional[float] = None
    average_buy_price: Optional[float] = None

    @field_validator("ticker", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        """Remove surrounding whitespace when a value is provided."""
        if isinstance(v, str):
            return v.strip()
        return v
