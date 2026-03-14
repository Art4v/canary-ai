"""
Router for the ``/database/portfolios`` endpoints.

Provides full CRUD: list all, get by username, create, update, delete.
All by-username operations resolve the username to user_id internally.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from supabase import Client

from dependencies import get_supabase_client
from schemas.response import success_response, error_response
from schemas.portfolios import PortfolioCreate, PortfolioUpdate
from crud import portfolios as crud_portfolios

router = APIRouter(prefix="/database/portfolios", tags=["portfolios"])


@router.get("")
def list_portfolios(db: Client = Depends(get_supabase_client)):
    """Return every row from the portfolios table."""
    data, err = crud_portfolios.get_all(db)
    if err:
        return JSONResponse(status_code=400, content=error_response(err))
    return success_response(data)


@router.get("/{username}")
def get_portfolio(username: str, db: Client = Depends(get_supabase_client)):
    """Return the portfolio belonging to *username*."""
    data, err = crud_portfolios.get_by_username(db, username)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)


@router.post("")
def create_portfolio(body: PortfolioCreate, db: Client = Depends(get_supabase_client)):
    """
    Create a new portfolio.

    Expects JSON with ``username``, ``cash_reserve``,
    ``total_capital_invested``, and ``current_portfolio_value``.
    """
    data, err = crud_portfolios.create(db, body.model_dump())
    if err:
        return JSONResponse(status_code=400, content=error_response(err))
    return success_response(data)


@router.put("/{username}")
def update_portfolio(username: str, body: PortfolioUpdate, db: Client = Depends(get_supabase_client)):
    """
    Update fields on the portfolio belonging to *username*.

    Only fields present in the request body are changed.
    """
    payload = body.model_dump(exclude_none=True)
    data, err = crud_portfolios.update_by_username(db, username, payload)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)


@router.delete("/{username}")
def delete_portfolio(username: str, db: Client = Depends(get_supabase_client)):
    """Delete the portfolio belonging to *username*."""
    data, err = crud_portfolios.delete_by_username(db, username)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))
    return success_response(data)
