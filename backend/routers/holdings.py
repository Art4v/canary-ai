"""
Router for the ``/database/holdings`` endpoints.

Provides full CRUD: list all, get by username, create, update, delete.
All by-username operations resolve username -> portfolio_id internally.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from supabase import Client

from dependencies import get_supabase_client
from schemas.response import success_response, error_response
from schemas.holdings import HoldingCreate, HoldingUpdate
from crud import holdings as crud_holdings

router = APIRouter(prefix="/database/holdings", tags=["holdings"])


@router.get("")
def list_holdings(db: Client = Depends(get_supabase_client)):
    """Return every row from the holdings table."""
    data, err = crud_holdings.get_all(db)
    if err:
        return JSONResponse(status_code=400, content=error_response(err))
    return success_response(data)


@router.get("/{username}")
def get_holdings(username: str, db: Client = Depends(get_supabase_client)):
    """Return all holdings for *username*'s portfolio."""
    data, err = crud_holdings.get_by_username(db, username)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)


@router.post("")
def create_holding(body: HoldingCreate, db: Client = Depends(get_supabase_client)):
    """
    Create a new holding.

    Expects JSON with ``username``, ``ticker``, ``quantity``, and
    ``average_buy_price``.
    """
    data, err = crud_holdings.create(db, body.model_dump())
    if err:
        return JSONResponse(status_code=400, content=error_response(err))
    return success_response(data)


@router.put("/{username}")
def update_holdings(username: str, body: HoldingUpdate, db: Client = Depends(get_supabase_client)):
    """
    Update fields on all holdings belonging to *username*.

    Only fields present in the request body are changed.
    """
    payload = body.model_dump(exclude_none=True)
    data, err = crud_holdings.update_by_username(db, username, payload)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)


@router.delete("/{username}")
def delete_holdings(username: str, db: Client = Depends(get_supabase_client)):
    """Delete all holdings belonging to *username*'s portfolio."""
    data, err = crud_holdings.delete_by_username(db, username)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)
