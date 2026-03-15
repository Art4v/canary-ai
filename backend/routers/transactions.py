"""
Router for the ``/database/transactions`` endpoints.

Provides full CRUD: list all, get by username, create, update, delete.
All by-username operations resolve username -> portfolio_id internally.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from supabase import Client

from dependencies import get_supabase_client, get_current_user
from schemas.response import success_response, error_response
from schemas.transactions import TransactionCreate, TransactionUpdate
from crud import transactions as crud_transactions

router = APIRouter(prefix="/database/transactions", tags=["transactions"])


@router.get("")
def list_transactions(db: Client = Depends(get_supabase_client)):
    """Return every row from the transactions table."""
    data, err = crud_transactions.get_all(db)
    if err:
        return JSONResponse(status_code=400, content=error_response(err))
    return success_response(data)


@router.get("/{username}")
def get_transactions(
    username: str,
    db: Client = Depends(get_supabase_client),
    _user: dict = Depends(get_current_user),
):
    """Return all transactions for *username*'s portfolio. Requires auth."""
    data, err = crud_transactions.get_by_username(db, username)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)


@router.post("")
def create_transaction(body: TransactionCreate, db: Client = Depends(get_supabase_client)):
    """
    Create a new transaction.

    Expects JSON with ``username``, ``ticker``, ``tx_type``,
    ``quantity``, ``price_per_unit``, and ``total_amount``.
    """
    data, err = crud_transactions.create(db, body.model_dump())
    if err:
        return JSONResponse(status_code=400, content=error_response(err))
    return success_response(data)


@router.put("/{username}")
def update_transactions(username: str, body: TransactionUpdate, db: Client = Depends(get_supabase_client)):
    """
    Update fields on all transactions belonging to *username*.

    Only fields present in the request body are changed.
    """
    payload = body.model_dump(exclude_none=True)
    data, err = crud_transactions.update_by_username(db, username, payload)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)


@router.delete("/{username}")
def delete_transactions(username: str, db: Client = Depends(get_supabase_client)):
    """Delete all transactions belonging to *username*'s portfolio."""
    data, err = crud_transactions.delete_by_username(db, username)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)
