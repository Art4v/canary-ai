"""
Shared resolution helpers for the CRUD layer.

Child tables (portfolios, holdings, transactions) are keyed by numeric
IDs internally, but the API is addressed by ``{username}``.  These
helpers perform the two-step lookup so every CRUD module stays DRY.
"""

from supabase import Client
from typing import Optional


def resolve_username_to_user_id(db: Client, username: str) -> Optional[str]:
    """
    Look up the ``user_id`` for a given username.

    Parameters
    ----------
    db : Client
        Initialised Supabase client.
    username : str
        The username to resolve.

    Returns
    -------
    str or None
        The ``user_id`` UUID string, or None if the username does not exist.
    """
    response = db.table("users").select("user_id").eq("username", username).execute()
    if response.data:
        return response.data[0]["user_id"]
    return None


def resolve_username_to_portfolio_id(db: Client, username: str) -> Optional[str]:
    """
    Look up the ``portfolio_id`` for a given username.

    Chains through the users table: username -> user_id -> portfolio_id.

    Parameters
    ----------
    db : Client
        Initialised Supabase client.
    username : str
        The username whose portfolio to find.

    Returns
    -------
    str or None
        The ``portfolio_id`` UUID string, or None if the user or portfolio
        does not exist.
    """
    user_id = resolve_username_to_user_id(db, username)
    if user_id is None:
        return None

    response = (
        db.table("portfolios")
        .select("portfolio_id")
        .eq("user_id", user_id)
        .execute()
    )
    if response.data:
        return response.data[0]["portfolio_id"]
    return None
