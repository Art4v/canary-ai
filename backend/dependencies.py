"""
Supabase client initialisation and FastAPI dependency.

Centralises the Supabase connection so every router/CRUD module can
inject the client via ``Depends(get_supabase_client)`` instead of
importing a global variable.
"""

import os
from dotenv import load_dotenv
from fastapi import HTTPException
from supabase import create_client, Client

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
