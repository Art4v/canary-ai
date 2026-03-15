"""
Supabase client initialisation and FastAPI dependencies.

Centralises the Supabase connection so every router/CRUD module can
inject the client via ``Depends(get_supabase_client)`` instead of
importing a global variable.

Also provides ``get_current_user`` — a FastAPI dependency that reads
the ``Authorization: Bearer <token>`` header, validates it against
the in-memory session store, and returns the session's user dict.
Protected endpoints should declare ``user=Depends(get_current_user)``.
"""

import os
from dotenv import load_dotenv
from fastapi import HTTPException, Request
from supabase import create_client, Client

from session_store import get_session

# Idempotent — safe to call even if main.py already loaded .env.
load_dotenv()

# Read Supabase credentials from environment variables.
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

# Module-level client singleton.  None when credentials are missing.
_supabase_client: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_supabase_client() -> Client:
    """
    FastAPI dependency that returns the Supabase client.

    Raises HTTP 503 when the client could not be initialised (missing
    SUPABASE_URL or SUPABASE_KEY in the environment).

    Returns
    -------
    Client
        An initialised supabase-py Client instance.
    """
    if _supabase_client is None:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured — set SUPABASE_URL and SUPABASE_KEY in .env",
        )
    return _supabase_client


def get_current_user(request: Request) -> dict:
    """
    FastAPI dependency that authenticates the caller via a Bearer token.

    Reads the ``Authorization`` header, extracts the token, and looks it
    up in the in-memory session store.  Returns the session dict
    (``user_id``, ``username``, ``created_at``) on success.

    Raises
    ------
    HTTPException 401
        If the header is missing, malformed, or the token is invalid/expired.

    Returns
    -------
    dict
        Session payload with at least ``user_id`` and ``username``.
    """
    # Read the Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    # Extract the token after "Bearer "
    token = auth_header[7:]
    session = get_session(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    return session
