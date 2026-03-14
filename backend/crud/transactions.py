"""
CRUD operations for the ``transactions`` table.

Transactions belong to a portfolio, so by-username operations resolve
username -> user_id -> portfolio_id before querying.
"""

from supabase import Client
from crud.helpers import resolve_username_to_portfolio_id


def get_all(db: Client) -> tuple[list[dict], str | None]:
    """Fetch every row from the transactions table."""
    response = db.table("transactions").select("*").execute()
    return response.data, None


def get_by_username(db: Client, username: str) -> tuple[list[dict] | None, str | None]:
    """
    Fetch all transactions for the portfolio belonging to *username*.

    Returns a list (many transactions per user), not a single row.
    """
    portfolio_id = resolve_username_to_portfolio_id(db, username)
    if portfolio_id is None:
        return None, f"User '{username}' or their portfolio not found"

    response = (
        db.table("transactions")
        .select("*")
        .eq("portfolio_id", portfolio_id)
        .execute()
    )
    return response.data, None


def create(db: Client, payload: dict) -> tuple[dict | None, str | None]:
    """
    Insert a new transaction row.

    *payload* must include ``username`` which is resolved to
    ``portfolio_id`` before insertion.
    """
    username = payload.pop("username", None)
    if not username:
        return None, "username is required"

    portfolio_id = resolve_username_to_portfolio_id(db, username)
    if portfolio_id is None:
        return None, f"User '{username}' or their portfolio not found"

    payload["portfolio_id"] = portfolio_id

    try:
        response = db.table("transactions").insert(payload).execute()
        return response.data[0] if response.data else None, None
    except Exception as exc:
        return None, str(exc)


def update_by_username(db: Client, username: str, payload: dict) -> tuple[list[dict] | None, str | None]:
    """
    Update fields on all transactions belonging to *username*'s portfolio.

    Only non-None fields in *payload* are sent.
    """
    if not payload:
        return None, "No fields to update"

    portfolio_id = resolve_username_to_portfolio_id(db, username)
    if portfolio_id is None:
        return None, f"User '{username}' or their portfolio not found"

    try:
        response = (
            db.table("transactions")
            .update(payload)
            .eq("portfolio_id", portfolio_id)
            .execute()
        )
        if not response.data:
            return None, f"No transactions found for user '{username}'"
        return response.data, None
    except Exception as exc:
        return None, str(exc)


def delete_by_username(db: Client, username: str) -> tuple[list[dict] | None, str | None]:
    """
    Delete all transactions belonging to *username*'s portfolio.

    Resolves username -> portfolio_id first.
    """
    portfolio_id = resolve_username_to_portfolio_id(db, username)
    if portfolio_id is None:
        return None, f"User '{username}' or their portfolio not found"

    response = (
        db.table("transactions")
        .delete()
        .eq("portfolio_id", portfolio_id)
        .execute()
    )
    if not response.data:
        return None, f"No transactions found for user '{username}'"
    return response.data, None
