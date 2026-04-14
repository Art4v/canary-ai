"""
Router for the ``/database/users`` endpoints.

Provides full CRUD: list all, get by username, create, update, delete.
Also handles login (returns a session token) and logout (invalidates it).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from supabase import Client

from dependencies import get_supabase_client, get_current_user
from schemas.response import success_response, error_response
from schemas.users import UserCreate, UserLogin, UserUpdate
from crud import users as crud_users
from crud import portfolios as crud_portfolios
from session_store import create_session, delete_session

# All routes are prefixed with /database/users by the include_router call.
router = APIRouter(prefix="/database/users", tags=["users"])


@router.get("")
def list_users(db: Client = Depends(get_supabase_client)):
    """Return every row from the users table."""
    data, err = crud_users.get_all(db)
    if err:
        return JSONResponse(status_code=400, content=error_response(err))
    return success_response(data)


@router.get("/{username}")
def get_user(
    username: str,
    db: Client = Depends(get_supabase_client),
    _user: dict = Depends(get_current_user),
):
    """Return a single user identified by *username*. Requires auth."""
    data, err = crud_users.get_by_username(db, username)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)


@router.post("/login")
def login_user(body: UserLogin, db: Client = Depends(get_supabase_client)):
    """
    Verify user credentials (email + password) and issue a session token.

    Looks up the user by email and checks the plaintext password
    against the stored bcrypt hash. On success, creates a server-side
    session and returns ``{ user: <user_data>, token: <session_token> }``.
    """
    data, err = crud_users.authenticate(db, body.email, body.password)
    if err:
        return JSONResponse(status_code=401, content=error_response(err))

    # Create a server-side session and return the token alongside user data
    token = create_session(data)
    return success_response({"user": data, "token": token})


@router.post("/logout")
def logout_user(request: Request):
    """
    Invalidate the caller's session token (logout).

    Reads the Bearer token from the Authorization header and removes
    it from the session store. Does NOT require ``Depends(get_current_user)``
    so that expired tokens can still be explicitly deleted.

    Returns success regardless of whether the token was found — the
    client should clear its local state either way.
    """
    # Extract token from Authorization header (if present)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    # Delete the session — returns True if it existed
    deleted = delete_session(token) if token else False
    return success_response({"logged_out": True, "session_existed": deleted})


@router.post("")
def create_user(body: UserCreate, db: Client = Depends(get_supabase_client)):
    """
    Create a new user.

    Expects JSON with ``username``, ``email``, and ``password``.
    The plaintext password is hashed server-side before storage.
    """
    # exclude_none=True omits Optional fields the caller didn't send,
    # so the database column defaults (e.g. notifications=true) take effect.
    data, err = crud_users.create(db, body.model_dump(exclude_none=True))
    if err:
        return JSONResponse(status_code=400, content=error_response(err))

    # Auto-create a zeroed-out portfolio for the new user.
    # This ensures every user has a portfolio row from the start.
    # If portfolio creation fails, log a warning but don't fail registration
    # — the user row already exists and portfolios can be created later.
    try:
        _portfolio_data, portfolio_err = crud_portfolios.create(db, {
            "username": body.username,
            "cash_reserve": 0,
            "total_capital_invested": 0,
            "current_portfolio_value": 0,
        })
        if portfolio_err:
            print(
                f"[Users] WARNING: failed to auto-create portfolio for "
                f"'{body.username}': {portfolio_err}",
                flush=True,
            )
    except Exception as exc:
        print(
            f"[Users] WARNING: exception creating portfolio for "
            f"'{body.username}': {exc}",
            flush=True,
        )

    return success_response(data)


@router.put("/{username}")
def update_user(
    username: str,
    body: UserUpdate,
    db: Client = Depends(get_supabase_client),
    _user: dict = Depends(get_current_user),
):
    """
    Update fields on an existing user. Requires auth.

    Only fields present in the request body are changed; omitted fields
    are left untouched.
    """
    # exclude_none=True drops Optional fields the caller didn't send.
    payload = body.model_dump(exclude_none=True)
    data, err = crud_users.update_by_username(db, username, payload)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)


@router.delete("/{username}")
def delete_user(username: str, db: Client = Depends(get_supabase_client)):
    """Delete a user identified by *username*."""
    data, err = crud_users.delete_by_username(db, username)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)
