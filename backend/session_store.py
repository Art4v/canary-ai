"""
In-memory session store with 24-hour TTL.

Maps UUID session tokens to user data (user_id, username, created_at).
Used by ``dependencies.get_current_user`` to verify incoming requests
and by the login/logout endpoints in ``routers/users.py`` to create
and destroy sessions.

Note: sessions live only in the server process — a backend restart
invalidates every active session, which is acceptable for a hackathon
demo.  For production, swap in Redis or a database-backed store.
"""

import uuid
from datetime import datetime, timedelta

# Session lifetime — tokens older than this are treated as expired.
_TTL = timedelta(hours=24)

# Internal store: token string → { user_id, username, created_at }
_sessions: dict[str, dict] = {}


def create_session(user_data: dict) -> str:
    """
    Create a new session for the given user and return the token.

    Parameters
    ----------
    user_data : dict
        Must contain at least ``user_id`` and ``username``.

    Returns
    -------
    str
        A UUID-based session token that the client should send as
        ``Authorization: Bearer <token>`` on subsequent requests.
    """
    token = str(uuid.uuid4())
    _sessions[token] = {
        "user_id": user_data["user_id"],
        "username": user_data["username"],
        "created_at": datetime.utcnow(),
    }
    return token


def get_session(token: str) -> dict | None:
    """
    Look up a session by token.

    Returns the session dict if the token exists **and** has not
    exceeded the 24-hour TTL.  Returns ``None`` for unknown or
    expired tokens (expired tokens are also deleted on access).

    Parameters
    ----------
    token : str
        The Bearer token sent by the client.

    Returns
    -------
    dict | None
        Session payload (``user_id``, ``username``, ``created_at``)
        or ``None``.
    """
    session = _sessions.get(token)
    if session is None:
        return None

    # Check TTL — delete if expired
    if datetime.utcnow() - session["created_at"] > _TTL:
        _sessions.pop(token, None)
        return None

    return session


def delete_session(token: str) -> bool:
    """
    Remove a session (logout).

    Parameters
    ----------
    token : str
        The Bearer token to invalidate.

    Returns
    -------
    bool
        ``True`` if the token existed (and was removed), ``False``
        if it was already gone or never existed.
    """
    return _sessions.pop(token, None) is not None
