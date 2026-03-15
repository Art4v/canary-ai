"""
Router for the ``/chat`` endpoints.

Exposes the chatbot advisor logic (from ``chatbot/advisor.py``) as a REST API
so the frontend ChatWindow can send messages and receive AI-powered responses.

Session state (conversation history, state machine position, pending stocks)
is stored in a module-level dict keyed by username.  Memory and preferences
are persisted to the Supabase ``users`` table (``memory`` and ``preferences``
columns) after each message.

Endpoints:
    POST /chat        — send a message and get a reply
    POST /chat/reset  — clear the session for a user (new conversation)
"""

import os
import json
import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from supabase import Client
from anthropic import Anthropic
from dotenv import load_dotenv

from dependencies import get_supabase_client
from schemas.response import success_response, error_response
from crud import users as crud_users
from crud import portfolios as crud_portfolios

# Import advisor functions — the chatbot logic lives in chatbot/advisor.py
from chatbot.advisor import (
    build_advisor_system_prompt,
    extract_preferences,
    validate_and_merge,
    _detect_new_tickers,
    _check_yes_no,
    add_stock_to_preferences,
    all_fields_collected,
    ConversationState,
    _MODEL,
    save_preferences,
)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

# Load .env for ANTHROPIC_API_KEY
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

# Initialise the Anthropic client once at module level
_api_key = os.getenv("ANTHROPIC_API_KEY", "")
_client: Anthropic | None = None
if _api_key and _api_key != "your_anthropic_api_key_here":
    _client = Anthropic(api_key=_api_key)

# All routes are prefixed with /chat
router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    """Request body for POST /chat.

    Attributes
    ----------
    message : str
        The user's message text.
    username : str
        Username of the logged-in user (used to load/save preferences and memory).
    """
    message: str
    username: str


class ChatReset(BaseModel):
    """Request body for POST /chat/reset.

    Attributes
    ----------
    username : str
        Username whose session should be cleared.
    """
    username: str


# ---------------------------------------------------------------------------
# Per-user session state — stored in memory (not DB) since it's ephemeral
# ---------------------------------------------------------------------------

# Each entry holds the state machine variables for one user's active session.
# Keyed by username string.
_sessions: dict[str, dict] = {}


def _get_or_create_session(username: str, collected: dict) -> dict:
    """
    Return the existing session for *username*, or create a fresh one.

    A new session starts in COLLECTING state (or ADVISING if all 4
    preference fields are already set from the DB).

    Parameters
    ----------
    username : str
        The user's login name.
    collected : dict
        Current preference fields loaded from the DB (may be empty).

    Returns
    -------
    dict
        Session dict with keys: messages, state, pending_stock, stock_queue,
        clarification_count, declined_stocks, collected.
    """
    if username not in _sessions:
        # Determine starting state based on whether preferences are complete
        initial_state = (
            ConversationState.ADVISING
            if all_fields_collected(collected)
            else ConversationState.COLLECTING
        )
        _sessions[username] = {
            "messages": [],                      # Anthropic SDK message history
            "state": initial_state,              # Current ConversationState
            "pending_stock": None,               # Ticker being discussed/confirmed
            "stock_queue": [],                   # Tickers waiting to be discussed
            "clarification_count": 0,            # Ambiguous yes/no counter
            "declined_stocks": set(),            # Tickers declined this session
            "collected": dict(collected),        # Working copy of preferences
        }
    return _sessions[username]


def _build_memory_entry(text: str, existing_memory: str) -> str:
    """
    Build an updated memory string by appending *text* under today's date header.

    Mirrors the logic of ``append_memory()`` in advisor.py but works on
    strings rather than files.

    Parameters
    ----------
    text : str
        The log line to append.
    existing_memory : str
        The current memory content from the DB.

    Returns
    -------
    str
        Updated memory string with the new entry appended.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    date_header = f"## {today}"

    # Start with existing memory (or empty string)
    memory = existing_memory or ""

    # Add the date header if it's not already present
    if date_header not in memory:
        if memory.strip():
            memory += "\n\n"
        memory += f"{date_header}\n"

    # Append the entry line
    memory += f"- {text}\n"
    return memory


# ---------------------------------------------------------------------------
# Auto-tracking helpers — bridge chatbot stock confirmations to the
# tracking / prediction systems defined in main.py.  Uses lazy imports
# (``import main`` inside function bodies) to avoid circular imports,
# since main.py imports this router at module level.
# ---------------------------------------------------------------------------


async def _auto_track_and_predict(ticker: str) -> None:
    """
    Start tracking *ticker* and ensure prediction / news loops are running.

    Called when the chatbot confirms a stock.  Idempotent — if the ticker
    is already tracked or loops are already running, this is a no-op for
    those items.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (will be uppercased).
    """
    import main  # lazy import to avoid circular dependency

    ticker = ticker.upper()

    # Start tracking this ticker if not already active
    if ticker not in main.stock_tasks:
        task = asyncio.create_task(main._track_ticker(ticker))
        main.stock_tasks[ticker] = task

    # Start the C++ efficient-frontier prediction loop if not running
    if main.prediction_task is None or main.prediction_task.done():
        main.prediction_task = asyncio.create_task(main._run_prediction_loop())

    # Start Finnhub news tracking if not running (required by news prediction)
    if main.news_task is None or main.news_task.done():
        finnhub_key = os.getenv("FINNHUB_API_KEY")
        if finnhub_key:
            main.news_task = asyncio.create_task(main._track_news())

    # Start the news-sentiment prediction loop if not running
    if main.news_prediction_task is None or main.news_prediction_task.done():
        main.news_prediction_task = asyncio.create_task(main._run_news_prediction_loop())


async def _auto_untrack_and_maybe_stop(ticker: str) -> None:
    """
    Stop tracking *ticker*.  If no tickers remain, stop prediction loops.

    Called when the chatbot removes a stock from the user's portfolio.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (will be uppercased).
    """
    import main  # lazy import to avoid circular dependency

    ticker = ticker.upper()

    # Cancel the tracking task for this ticker
    task = main.stock_tasks.pop(ticker, None)
    if task:
        task.cancel()

    # If no tickers remain, shut down prediction and news-prediction loops
    if not main.stock_tasks:
        if main.prediction_task is not None:
            main.prediction_task.cancel()
            main.prediction_task = None
        if main.news_prediction_task is not None:
            main.news_prediction_task.cancel()
            main.news_prediction_task = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
async def chat(body: ChatMessage, db: Client = Depends(get_supabase_client)):
    """
    Process a single chat message and return the advisor's reply.

    Flow:
    1. Load user's memory and preferences from Supabase
    2. Run the state machine logic (extract preferences, handle stock
       discussions, generate Claude response)
    3. Save updated memory/preferences back to Supabase
    4. Return the reply, any updated preferences, and the current state

    Parameters
    ----------
    body : ChatMessage
        Contains ``message`` (user text) and ``username``.
    db : Client
        Supabase client injected via FastAPI Depends.

    Returns
    -------
    JSONResponse
        ``{ "reply": str, "preferences_updated": dict, "memory_entry": str|null, "state": str }``
    """
    # Guard: Anthropic client must be configured
    if _client is None:
        return JSONResponse(
            status_code=503,
            content=error_response(
                "ANTHROPIC_API_KEY is not configured — add it to backend/.env"
            ),
        )

    # --- Load user data from DB ---
    user_data, err = crud_users.get_by_username(db, body.username)
    if err:
        return JSONResponse(status_code=404, content=error_response(err))

    # Parse preferences from the DB (JSONB column, may be None or a JSON string)
    db_preferences = user_data.get("preferences") or {}
    # If Supabase returned a JSON string instead of a parsed dict, decode it
    if isinstance(db_preferences, str):
        try:
            db_preferences = json.loads(db_preferences)
        except (json.JSONDecodeError, TypeError):
            db_preferences = {}
    # Remove the saved_at timestamp if present — it's metadata, not a preference
    if isinstance(db_preferences, dict):
        db_preferences.pop("saved_at", None)
    else:
        db_preferences = {}

    # Load memory text from the DB (text column, may be None)
    memory_content = user_data.get("memory") or ""

    # --- Fetch portfolio data for contextual advice ---
    # The advisor uses this to reference the user's cash, invested capital,
    # and current portfolio value when making suggestions.
    portfolio_summary = None
    try:
        portfolio_data, portfolio_err = crud_portfolios.get_by_username(db, body.username)
        if not portfolio_err and portfolio_data:
            portfolio_summary = {
                "cash_reserve": float(portfolio_data.get("cash_reserve", 0)),
                "total_capital_invested": float(portfolio_data.get("total_capital_invested", 0)),
                "current_portfolio_value": float(portfolio_data.get("current_portfolio_value", 0)),
            }
    except Exception as exc:
        # Non-fatal — chat works without portfolio context
        print(f"[Chat] WARNING: failed to fetch portfolio for {body.username}: {exc}", flush=True)

    # --- Get or create session ---
    session = _get_or_create_session(body.username, db_preferences)
    collected = session["collected"]
    messages = session["messages"]
    state = session["state"]
    pending_stock = session["pending_stock"]
    stock_queue = session["stock_queue"]
    clarification_count = session["clarification_count"]
    declined_stocks = session["declined_stocks"]

    # Track what gets updated this turn for the response
    preferences_updated = {}
    memory_entry = None

    # Append the user message to conversation history
    user_input = body.message.strip()
    if not user_input:
        return JSONResponse(
            status_code=400,
            content=error_response("Message cannot be empty"),
        )
    messages.append({"role": "user", "content": user_input})

    reply = ""

    # =================================================================
    # STATE: CONFIRMING_STOCK — check yes/no/ambiguous before Claude call
    # =================================================================
    if state == ConversationState.CONFIRMING_STOCK:
        decision = _check_yes_no(user_input)

        if decision == "yes":
            # User confirmed — add the stock
            if "stocks_to_keep" not in collected or collected["stocks_to_keep"] is None:
                collected["stocks_to_keep"] = []
            if pending_stock not in collected["stocks_to_keep"]:
                collected["stocks_to_keep"].append(pending_stock)

            preferences_updated[f"stocks_to_keep (+{pending_stock})"] = collected["stocks_to_keep"]

            # Auto-start tracking and prediction for the confirmed stock
            try:
                await _auto_track_and_predict(pending_stock)
            except Exception as exc:
                print(f"[Chat] WARNING: auto-track failed for {pending_stock}: {exc}", flush=True)

            memory_entry = f"User confirmed adding {pending_stock} to portfolio"
            memory_content = _build_memory_entry(memory_entry, memory_content)

            # Pop next stock or return to previous state
            if stock_queue:
                pending_stock = stock_queue.pop(0)
                state = ConversationState.CONFIRMING_STOCK
                clarification_count = 0
            else:
                pending_stock = None
                clarification_count = 0
                state = (
                    ConversationState.ADVISING
                    if all_fields_collected(collected)
                    else ConversationState.COLLECTING
                )

        elif decision == "no":
            # User declined
            memory_entry = f"User declined adding {pending_stock} to portfolio"
            memory_content = _build_memory_entry(memory_entry, memory_content)
            declined_stocks.add(pending_stock)

            if stock_queue:
                pending_stock = stock_queue.pop(0)
                state = ConversationState.CONFIRMING_STOCK
                clarification_count = 0
            else:
                pending_stock = None
                clarification_count = 0
                state = (
                    ConversationState.ADVISING
                    if all_fields_collected(collected)
                    else ConversationState.COLLECTING
                )

        else:
            # Ambiguous — clarify or drop after 2 attempts
            clarification_count += 1
            if clarification_count >= 2:
                memory_entry = f"Dropped {pending_stock} after ambiguous responses (not committed)"
                memory_content = _build_memory_entry(memory_entry, memory_content)
                declined_stocks.add(pending_stock)

                if stock_queue:
                    pending_stock = stock_queue.pop(0)
                    state = ConversationState.CONFIRMING_STOCK
                    clarification_count = 0
                else:
                    pending_stock = None
                    clarification_count = 0
                    state = (
                        ConversationState.ADVISING
                        if all_fields_collected(collected)
                        else ConversationState.COLLECTING
                    )

        # Generate Claude response for this confirmation state
        system_prompt = build_advisor_system_prompt(
            collected, memory_content, state, pending_stock,
            portfolio_summary=portfolio_summary,
        )
        try:
            response = _client.messages.create(
                model=_MODEL, max_tokens=256,
                system=system_prompt, messages=messages,
            )
            reply = response.content[0].text
            messages.append({"role": "assistant", "content": reply})
        except Exception as exc:
            messages.pop()  # Remove the user message on failure
            return JSONResponse(
                status_code=502,
                content=error_response(f"Claude API error: {exc}"),
            )

        # Save session state and persist to DB
        session.update({
            "state": state, "pending_stock": pending_stock,
            "stock_queue": stock_queue,
            "clarification_count": clarification_count,
            "declined_stocks": declined_stocks, "collected": collected,
        })
        _persist_to_db(db, body.username, collected, memory_content)

        return success_response({
            "reply": reply,
            "preferences_updated": preferences_updated,
            "memory_entry": memory_entry,
            "state": state,
        })

    # =================================================================
    # STATE: DISCUSSING_STOCK — Claude discusses, then move to CONFIRMING
    # =================================================================
    if state == ConversationState.DISCUSSING_STOCK:
        system_prompt = build_advisor_system_prompt(
            collected, memory_content, state, pending_stock,
            portfolio_summary=portfolio_summary,
        )
        try:
            response = _client.messages.create(
                model=_MODEL, max_tokens=256,
                system=system_prompt, messages=messages,
            )
            reply = response.content[0].text
            messages.append({"role": "assistant", "content": reply})
        except Exception as exc:
            messages.pop()
            return JSONResponse(
                status_code=502,
                content=error_response(f"Claude API error: {exc}"),
            )

        # After discussion, move to confirmation
        state = ConversationState.CONFIRMING_STOCK
        clarification_count = 0

        session.update({
            "state": state, "pending_stock": pending_stock,
            "clarification_count": clarification_count,
        })

        return success_response({
            "reply": reply,
            "preferences_updated": {},
            "memory_entry": None,
            "state": state,
        })

    # =================================================================
    # STATE: COLLECTING or ADVISING — extract fields, handle stocks
    # =================================================================

    # Extract preference fields from the user's latest message
    extracted = extract_preferences(_client, messages, collected)

    # Handle stock removals
    stocks_to_remove = extracted.get("stocks_to_remove", []) if extracted else []
    if isinstance(stocks_to_remove, list) and stocks_to_remove:
        current_stocks = collected.get("stocks_to_keep") or []
        for ticker in stocks_to_remove:
            ticker = ticker.upper() if isinstance(ticker, str) else str(ticker)
            if ticker in current_stocks:
                current_stocks.remove(ticker)

                # Auto-stop tracking for the removed stock; stop loops if none remain
                try:
                    await _auto_untrack_and_maybe_stop(ticker)
                except Exception as exc:
                    print(f"[Chat] WARNING: auto-untrack failed for {ticker}: {exc}", flush=True)

                preferences_updated[f"stocks_to_keep (-{ticker})"] = current_stocks
                entry = f"User removed {ticker} from portfolio"
                memory_content = _build_memory_entry(entry, memory_content)
                if memory_entry is None:
                    memory_entry = entry
        collected["stocks_to_keep"] = current_stocks

    # Detect new tickers that need discussion
    new_tickers = (
        _detect_new_tickers(extracted, collected, declined_stocks)
        if extracted else []
    )

    # Validate and merge non-stock fields
    extracted_without_stocks = {
        k: v for k, v in extracted.items()
        if k not in ("stocks_to_keep", "stocks_to_remove")
    }
    if extracted_without_stocks:
        updated = validate_and_merge(extracted_without_stocks, collected)
        if updated:
            for field in updated:
                preferences_updated[field] = collected[field]
                # Log field updates to memory
                if field == "cash_reserve":
                    entry = f"Cash reserve set to ${collected['cash_reserve']:,.2f}"
                    memory_content = _build_memory_entry(entry, memory_content)
                    memory_entry = entry
                elif field == "trading_style":
                    entry = f"Trading style set to {collected['trading_style']}"
                    memory_content = _build_memory_entry(entry, memory_content)
                    memory_entry = entry
                elif field == "stock_preferences":
                    prefs = collected["stock_preferences"]
                    if prefs:
                        entry = f"Stock preferences set to: {', '.join(prefs)}"
                        memory_content = _build_memory_entry(entry, memory_content)
                        memory_entry = entry

    # Check if we should transition to ADVISING
    if state == ConversationState.COLLECTING and all_fields_collected(collected):
        state = ConversationState.ADVISING

    # If new tickers were mentioned, queue them for discussion
    if new_tickers:
        pending_stock = new_tickers[0]
        stock_queue.extend(new_tickers[1:])
        state = ConversationState.DISCUSSING_STOCK
        clarification_count = 0

        # Generate Claude's discussion of this stock
        system_prompt = build_advisor_system_prompt(
            collected, memory_content, state, pending_stock,
            portfolio_summary=portfolio_summary,
        )
        try:
            response = _client.messages.create(
                model=_MODEL, max_tokens=256,
                system=system_prompt, messages=messages,
            )
            reply = response.content[0].text
            messages.append({"role": "assistant", "content": reply})
        except Exception as exc:
            messages.pop()
            return JSONResponse(
                status_code=502,
                content=error_response(f"Claude API error: {exc}"),
            )

        # After discussion reply, move to confirmation
        state = ConversationState.CONFIRMING_STOCK

        session.update({
            "state": state, "pending_stock": pending_stock,
            "stock_queue": stock_queue,
            "clarification_count": clarification_count,
            "declined_stocks": declined_stocks, "collected": collected,
        })
        _persist_to_db(db, body.username, collected, memory_content)

        return success_response({
            "reply": reply,
            "preferences_updated": preferences_updated,
            "memory_entry": memory_entry,
            "state": state,
        })

    # No new stocks — generate a normal conversational response
    system_prompt = build_advisor_system_prompt(
        collected, memory_content, state, pending_stock,
        portfolio_summary=portfolio_summary,
    )
    try:
        response = _client.messages.create(
            model=_MODEL, max_tokens=256,
            system=system_prompt, messages=messages,
        )
        reply = response.content[0].text
        messages.append({"role": "assistant", "content": reply})
    except Exception as exc:
        messages.pop()
        return JSONResponse(
            status_code=502,
            content=error_response(f"Claude API error: {exc}"),
        )

    # Save session state and persist to DB
    session.update({
        "state": state, "pending_stock": pending_stock,
        "stock_queue": stock_queue,
        "clarification_count": clarification_count,
        "declined_stocks": declined_stocks, "collected": collected,
    })
    _persist_to_db(db, body.username, collected, memory_content)

    return success_response({
        "reply": reply,
        "preferences_updated": preferences_updated,
        "memory_entry": memory_entry,
        "state": state,
    })


@router.post("/reset")
def reset_chat(body: ChatReset):
    """
    Clear the server-side chat session for a user.

    Removes the in-memory session state so the next POST /chat starts
    fresh.  Does NOT clear the user's persisted memory or preferences
    in the database — those carry over to the new session.

    Parameters
    ----------
    body : ChatReset
        Contains ``username`` whose session to clear.

    Returns
    -------
    dict
        ``{ "success": true, "data": { "cleared": true } }``
    """
    if body.username in _sessions:
        del _sessions[body.username]
    return success_response({"cleared": True})


# ---------------------------------------------------------------------------
# DB persistence helper
# ---------------------------------------------------------------------------

def _persist_to_db(db: Client, username: str, collected: dict, memory: str) -> None:
    """
    Write the current preferences and memory back to the Supabase users table.

    Adds a ``saved_at`` timestamp to preferences for tracking.  Errors are
    logged but not raised — chat should not fail because of a DB write error.

    Parameters
    ----------
    db : Client
        Supabase client.
    username : str
        User to update.
    collected : dict
        Current collected preferences.
    memory : str
        Current memory text.
    """
    try:
        # Add a timestamp so we know when preferences were last saved
        prefs_with_ts = {**collected, "saved_at": datetime.now().isoformat()}
        payload = {
            "preferences": prefs_with_ts,
            "memory": memory,
        }
        db.table("users").update(payload).eq("username", username).execute()
    except Exception as exc:
        # Non-fatal — log and continue so the chat response still returns
        print(f"[Chat] WARNING: failed to persist to DB for {username}: {exc}", flush=True)
