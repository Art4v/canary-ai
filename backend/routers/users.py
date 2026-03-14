"""
Router for the ``/database/users`` endpoints.

Provides full CRUD: list all, get by username, create, update, delete.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from supabase import Client

from dependencies import get_supabase_client
from schemas.response import success_response, error_response
from schemas.users import UserCreate, UserLogin, UserUpdate
from crud import users as crud_users

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
def get_user(username: str, db: Client = Depends(get_supabase_client)):
    """Return a single user identified by *username*."""
    data, err = crud_users.get_by_username(db, username)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)


@router.post("/login")
def login_user(body: UserLogin, db: Client = Depends(get_supabase_client)):
    """
    Verify user credentials (email + password).

    Looks up the user by email and checks the plaintext password
    against the stored bcrypt hash. Returns user data on success.
    No JWT/session is created — this is credential verification only.
    """
    data, err = crud_users.authenticate(db, body.email, body.password)
    if err:
        return JSONResponse(status_code=401, content=error_response(err))
    return success_response(data)


@router.post("")
def create_user(body: UserCreate, db: Client = Depends(get_supabase_client)):
    """
    Create a new user.

    Expects JSON with ``username``, ``email``, and ``password``.
    The plaintext password is hashed server-side before storage.
    """
    # model_dump() converts the Pydantic model to a plain dict for Supabase.
    data, err = crud_users.create(db, body.model_dump())
    if err:
        return JSONResponse(status_code=400, content=error_response(err))
    return success_response(data)


@router.put("/{username}")
def update_user(username: str, body: UserUpdate, db: Client = Depends(get_supabase_client)):
    """
    Update fields on an existing user.

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
