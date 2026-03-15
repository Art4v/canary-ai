"""
CRUD operations for the ``users`` table.

All functions return a ``(data, error_string | None)`` tuple so the
router can decide the HTTP status code without catching exceptions.

Passwords are hashed with bcrypt before being stored in the database.
"""

from supabase import Client
import bcrypt


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


def _hash_password(plaintext: str) -> str:
    """Hash a plaintext password with bcrypt and return the UTF-8 hash string.

    Uses bcrypt's default work factor (12 rounds) for a good balance
    between security and hashing speed.
    """
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Check a plaintext password against a bcrypt hash.

    Returns True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))


def create(db: Client, payload: dict) -> tuple[dict | None, str | None]:
    """
    Insert a new user row.

    Parameters
    ----------
    payload : dict
        Must contain ``username``, ``email``, ``password``.
        The plaintext ``password`` is hashed with bcrypt and stored
        as ``password_hash`` in the database.

    Returns (inserted_row, None) or (None, error_msg) on duplicate / DB error.
    """
    try:
        # Extract the plaintext password and replace it with a bcrypt hash.
        # The database column is ``password_hash``, so we swap the key name.
        plaintext = payload.pop("password")
        payload["password_hash"] = _hash_password(plaintext)

        # If an API key is provided, hash it with bcrypt before storage.
        # The database stores only the hash — the plaintext key is never persisted.
        if "api_key" in payload and payload["api_key"] is not None:
            payload["api_key"] = _hash_password(payload["api_key"])

        response = db.table("users").insert(payload).execute()
        return response.data[0] if response.data else None, None
    except Exception as exc:
        return None, str(exc)


def update_by_username(db: Client, username: str, payload: dict) -> tuple[dict | None, str | None]:
    """
    Update fields on an existing user identified by username.

    Only non-None fields in *payload* are sent to Supabase.
    If ``password`` is present, it is hashed with bcrypt and stored
    as ``password_hash`` in the database.

    Returns (updated_row, None) or (None, error_msg).
    """
    if not payload:
        return None, "No fields to update"

    # If a new plaintext password was supplied, hash it and swap the key
    # to match the database column name (``password_hash``).
    if "password" in payload:
        plaintext = payload.pop("password")
        payload["password_hash"] = _hash_password(plaintext)

    # If an API key is provided, hash it with bcrypt before storage.
    # The database stores only the hash — the plaintext key is never persisted.
    if "api_key" in payload and payload["api_key"] is not None:
        payload["api_key"] = _hash_password(payload["api_key"])

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


def get_by_email(db: Client, email: str) -> tuple[dict | None, str | None]:
    """
    Fetch a single user by email address.

    Returns (row_dict, None) on success or (None, error_msg) when not found.
    """
    response = db.table("users").select("*").eq("email", email).execute()
    if not response.data:
        return None, f"No account found with email '{email}'"
    return response.data[0], None


def authenticate(db: Client, email: str, password: str) -> tuple[dict | None, str | None]:
    """
    Verify a user's credentials by email and plaintext password.

    Looks up the user by email, then checks the plaintext password
    against the stored bcrypt hash. Returns the user row (without
    password_hash) on success, or an error string on failure.
    """
    # Look up the user by email
    user, err = get_by_email(db, email)
    if err:
        # Use a generic message to avoid leaking whether the email exists
        return None, "Invalid email or password"

    # Verify the plaintext password against the stored bcrypt hash
    if not verify_password(password, user.get("password_hash", "")):
        return None, "Invalid email or password"

    # Remove password_hash from the response for security
    user_safe = {k: v for k, v in user.items() if k != "password_hash"}
    return user_safe, None


def delete_by_username(db: Client, username: str) -> tuple[dict | None, str | None]:
    """
    Delete a user by username.

    Returns (deleted_row, None) or (None, error_msg).
    """
    response = db.table("users").delete().eq("username", username).execute()
    if not response.data:
        return None, f"User '{username}' not found"
    return response.data[0], None
