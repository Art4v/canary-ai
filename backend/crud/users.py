"""
CRUD operations for the ``users`` table.

All functions return a ``(data, error_string | None)`` tuple so the
router can decide the HTTP status code without catching exceptions.
"""

from supabase import Client


def get_all(db: Client) -> tuple[list[dict], str | None]:
    """Fetch every row from the users table."""
    response = db.table("users").select("*").execute()
    return response.data, None


def get_by_username(db: Client, username: str) -> tuple[dict | None, str | None]:
    """
    Fetch a single user by username.

    Returns (row_dict, None) on success or (None, error_msg) when not found.
    """
    response = db.table("users").select("*").eq("username", username).execute()
    if not response.data:
        return None, f"User '{username}' not found"
    return response.data[0], None


def create(db: Client, payload: dict) -> tuple[dict | None, str | None]:
    """
    Insert a new user row.

    Parameters
    ----------
    payload : dict
        Must contain ``username``, ``email``, ``password_hash``.

    Returns (inserted_row, None) or (None, error_msg) on duplicate / DB error.
    """
    try:
        response = db.table("users").insert(payload).execute()
        return response.data[0] if response.data else None, None
    except Exception as exc:
        return None, str(exc)


def update_by_username(db: Client, username: str, payload: dict) -> tuple[dict | None, str | None]:
    """
    Update fields on an existing user identified by username.

    Only non-None fields in *payload* are sent to Supabase.

    Returns (updated_row, None) or (None, error_msg).
    """
    if not payload:
        return None, "No fields to update"

    try:
        response = (
            db.table("users")
            .update(payload)
            .eq("username", username)
            .execute()
        )
        if not response.data:
            return None, f"User '{username}' not found"
        return response.data[0], None
    except Exception as exc:
        return None, str(exc)


def delete_by_username(db: Client, username: str) -> tuple[dict | None, str | None]:
    """
    Delete a user by username.

    Returns (deleted_row, None) or (None, error_msg).
    """
    response = db.table("users").delete().eq("username", username).execute()
    if not response.data:
        return None, f"User '{username}' not found"
    return response.data[0], None
