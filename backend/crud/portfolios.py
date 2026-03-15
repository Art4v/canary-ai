"""
CRUD operations for the ``portfolios`` table.

Portfolios belong to a user, so all by-username operations first
resolve the username to a user_id via the helpers module.
"""

from supabase import Client
from crud.helpers import resolve_username_to_user_id


def get_all(db: Client) -> tuple[list[dict], str | None]:
    """Fetch every row from the portfolios table."""
    response = db.table("portfolios").select("*").execute()
    return response.data, None


def get_by_username(db: Client, username: str) -> tuple[dict | None, str | None]:
    """
    Fetch the portfolio belonging to *username*.

    Resolves username -> user_id, then queries portfolios by user_id.
    """
    user_id = resolve_username_to_user_id(db, username)
    if user_id is None:
        return None, f"User '{username}' not found"

    response = db.table("portfolios").select("*").eq("user_id", user_id).execute()
    if not response.data:
        return None, f"Portfolio for user '{username}' not found"
    return response.data[0], None


def create(db: Client, payload: dict) -> tuple[dict | None, str | None]:
    """
    Insert a new portfolio row.

    *payload* must include a ``username`` key which is resolved to
    ``user_id`` before insertion.
    """
    username = payload.pop("username", None)
    if not username:
        return None, "username is required"

    user_id = resolve_username_to_user_id(db, username)
    if user_id is None:
        return None, f"User '{username}' not found"

    payload["user_id"] = user_id

    try:
        response = db.table("portfolios").insert(payload).execute()
        return response.data[0] if response.data else None, None
    except Exception as exc:
        return None, str(exc)


def update_by_username(db: Client, username: str, payload: dict) -> tuple[dict | None, str | None]:
    """
    Update fields on the portfolio belonging to *username*.

    Only non-None fields in *payload* are sent.
    """
    if not payload:
        return None, "No fields to update"

    user_id = resolve_username_to_user_id(db, username)
    if user_id is None:
        return None, f"User '{username}' not found"

    try:
        response = (
            db.table("portfolios")
            .update(payload)
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data:
            return None, f"Portfolio for user '{username}' not found"
        return response.data[0], None
    except Exception as exc:
        return None, str(exc)


def deposit(db: Client, username: str, amount: float) -> tuple[dict | None, str | None]:
    """
    Deposit cash into the user's portfolio.

    Increases cash_reserve and current_portfolio_value by *amount*.
    total_capital_invested stays unchanged (deposits are not stock investments).
    """
    portfolio, err = get_by_username(db, username)
    if err:
        return None, err

    new_cash = float(portfolio["cash_reserve"]) + amount
    new_value = float(portfolio["current_portfolio_value"]) + amount

    return update_by_username(db, username, {
        "cash_reserve": new_cash,
        "current_portfolio_value": new_value,
    })


def withdraw(db: Client, username: str, amount: float) -> tuple[dict | None, str | None]:
    """
    Withdraw cash from the user's portfolio.

    Decreases cash_reserve and current_portfolio_value by *amount*.
    Returns an error if the withdrawal exceeds the available cash reserve.
    """
    portfolio, err = get_by_username(db, username)
    if err:
        return None, err

    current_cash = float(portfolio["cash_reserve"])
    if amount > current_cash:
        return None, "Insufficient cash reserve"

    new_cash = current_cash - amount
    new_value = float(portfolio["current_portfolio_value"]) - amount

    return update_by_username(db, username, {
        "cash_reserve": new_cash,
        "current_portfolio_value": new_value,
    })


def delete_by_username(db: Client, username: str) -> tuple[dict | None, str | None]:
    """
    Delete the portfolio belonging to *username*.

    Resolves username -> user_id first.
    """
    user_id = resolve_username_to_user_id(db, username)
    if user_id is None:
        return None, f"User '{username}' not found"

    response = db.table("portfolios").delete().eq("user_id", user_id).execute()
    if not response.data:
        return None, f"Portfolio for user '{username}' not found"
    return response.data[0], None
