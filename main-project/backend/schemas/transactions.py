"""
Pydantic schemas for the ``transactions`` table.

Includes a ``TxType`` enum that restricts the ``tx_type`` field to
buy / sell / hold — matching the values the C++ prediction module emits.
"""

from enum import Enum
from pydantic import BaseModel, field_validator
from typing import Optional


class TxType(str, Enum):
    """Allowed transaction types — mirrors the C++ output actions."""

    buy = "buy"
    sell = "sell"
    hold = "hold"


class TransactionCreate(BaseModel):
    """Schema for creating a new transaction row."""

    username: str              # resolved to portfolio_id via user -> portfolio chain
    ticker: str                # stock ticker symbol
    tx_type: TxType            # buy / sell / hold
    quantity: float            # number of shares transacted
    price_per_unit: float      # price at the time of transaction
    total_amount: float        # quantity * price_per_unit (or custom)

    @field_validator("username", "ticker", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove surrounding whitespace from string fields."""
        if isinstance(v, str):
            return v.strip()
        return v


class TransactionUpdate(BaseModel):
    """Schema for updating an existing transaction — all fields optional."""

    ticker: Optional[str] = None
    tx_type: Optional[TxType] = None
    quantity: Optional[float] = None
    price_per_unit: Optional[float] = None
    total_amount: Optional[float] = None

    @field_validator("ticker", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        """Remove surrounding whitespace when a value is provided."""
        if isinstance(v, str):
            return v.strip()
        return v
