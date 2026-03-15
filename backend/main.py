"""
FastAPI backend for Canary AI.

Provides live stock-tracking endpoints (yfinance), a general-news
tracking endpoint (Finnhub), and a prediction loop that runs the
compiled C++ efficient-frontier optimizer on demand.

All data sources are polled every POLL_INTERVAL_SECONDS and persisted
to CSV files that are wiped on every server startup.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta, timezone
import yfinance as yf
import asyncio
import csv
import os
import shutil
import requests
from dotenv import load_dotenv
import anthropic

# News-prediction helpers — sentiment overlay that adjusts the C++ trade plan.
from news_prediction.news_prediction import (
    load_news_csv,
    load_portfolio_csv,
    load_holdings_csv,
    build_prompt,
    call_claude,
    validate_response,
    write_portfolio_csv,
)

# Supabase client singleton — used directly (outside FastAPI Depends) by
# the prediction loop to sync portfolio state with the database.
from dependencies import _supabase_client

# Username-to-portfolio-ID resolver for fetching the right portfolio row.
from crud.helpers import resolve_username_to_portfolio_id

# Database routers — each provides full CRUD for one Supabase table.
from routers import users as users_router
from routers import portfolios as portfolios_router
from routers import holdings as holdings_router
from routers import transactions as transactions_router
from schemas.response import error_response

load_dotenv()

app = FastAPI()

# Absolute path to the built React frontend — resolves correctly regardless
# of the working directory (e.g. `python main.py` from backend/ or
# `python backend/main.py` from repo root).
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIST = os.path.join(_BACKEND_DIR, "..", "frontend", "dist")

# ── Configuration ─────────────────────────────────────────────────────────────

DATA_DIR = "data"
STOCK_DATA_DIR = os.path.join(DATA_DIR, "stock_training_data")
NEWS_DIR = os.path.join(DATA_DIR, "news")
PREDICTIONS_DIR = "trades"

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"

# Shared by the stock, news, and prediction polling loops.
POLL_INTERVAL_SECONDS = 60

# Shift the app's clock N hours into the past so yfinance returns data from
# that earlier window and Finnhub news is filtered to exclude articles
# published after the simulated time. When 0 or unset, behaviour is
# identical to real-time.
TIME_REWIND_HOURS = float(os.getenv("TIME_REWIND_HOURS", "0"))

NEWS_CSV_COLUMNS = [
    "id", "category", "datetime", "headline",
    "source", "summary", "url", "image", "related",
]

# Path to the compiled C++ binary — relative to the working directory
# (i.e. run uvicorn from backend/). On Windows the .exe variant is used
# automatically if present.
_PREDICTION_BIN_WIN  = os.path.join("prediction", "prediction.exe")
_PREDICTION_BIN_UNIX = os.path.join("prediction", "prediction")
PREDICTION_BIN = _PREDICTION_BIN_WIN if os.path.exists(_PREDICTION_BIN_WIN) else _PREDICTION_BIN_UNIX

# ── Time simulation ───────────────────────────────────────────────────────────

def _simulated_now() -> datetime:
    """
    Return the current UTC-aware datetime offset by TIME_REWIND_HOURS.

    When TIME_REWIND_HOURS is 0 (the default), the returned value equals
    the real wall-clock time — timedelta(hours=0) is a no-op.
    """
    return datetime.now(timezone.utc) - timedelta(hours=TIME_REWIND_HOURS)


# ── State ─────────────────────────────────────────────────────────────────────

# Active background tasks keyed by uppercase ticker symbol.
stock_tasks: dict[str, asyncio.Task] = {}

news_task: asyncio.Task | None = None

prediction_task: asyncio.Task | None = None

# Background task for the news-sentiment prediction loop (mirrors prediction_task).
news_prediction_task: asyncio.Task | None = None

# Tracks the last modification time of news.csv so the news prediction
# loop can skip Claude calls when news hasn't changed since last cycle.
_last_news_csv_mtime: float = 0.0

# Tracks Finnhub article IDs already persisted so duplicate articles
# across polling cycles are never written twice.
seen_news_ids: set[int] = set()

# Cached portfolio_id for user "a" — resolved once from Supabase on the
# first prediction cycle, then reused so we don't re-query every loop.
_cached_portfolio_id: str | None = None


# ── Supabase helpers for the prediction loop ─────────────────────────────────

def get_supabase_client_direct():
    """
    Return the module-level Supabase client singleton.

    Unlike ``get_supabase_client()`` in dependencies.py this does NOT use
    FastAPI ``Depends`` — it is safe to call from plain async helpers and
    background tasks.

    Raises
    ------
    RuntimeError
        If Supabase credentials are not configured (client is None).
    """
    if _supabase_client is None:
        raise RuntimeError(
            "Supabase client is not initialised — set SUPABASE_URL and "
            "SUPABASE_KEY in .env"
        )
    return _supabase_client


def fetch_portfolio_state(supabase) -> dict:
    """
    Fetch the current portfolio state from Supabase for user "a".

    On the first call, resolves the username to a portfolio_id and caches
    the result in ``_cached_portfolio_id`` so subsequent calls skip the
    lookup.

    Parameters
    ----------
    supabase : supabase.Client
        Initialised Supabase client.

    Returns
    -------
    dict
        Keys: ``portfolio_id``, ``cash_reserve``, ``total_capital``,
        ``investable_capital``.

    Raises
    ------
    RuntimeError
        If user "a" or their portfolio cannot be found.
    """
    global _cached_portfolio_id

    # Resolve username → portfolio_id once, then cache.
    if _cached_portfolio_id is None:
        pid = resolve_username_to_portfolio_id(supabase, "a")
        if pid is None:
            raise RuntimeError("Could not resolve username 'a' to a portfolio_id")
        _cached_portfolio_id = pid

    portfolio_id = _cached_portfolio_id

    # Fetch the portfolio row for the resolved ID.
    response = (
        supabase.table("portfolios")
        .select("cash_reserve, current_portfolio_value")
        .eq("portfolio_id", portfolio_id)
        .execute()
    )

    if not response.data:
        raise RuntimeError(f"No portfolio row found for portfolio_id={portfolio_id}")

    row = response.data[0]
    cash_reserve = float(row["cash_reserve"])
    current_value = float(row["current_portfolio_value"])

    # Derive capital figures from DB state.
    total_capital = cash_reserve + current_value
    investable_capital = total_capital * 0.90  # 90% of total is investable

    return {
        "portfolio_id": portfolio_id,
        "cash_reserve": cash_reserve,
        "total_capital": total_capital,
        "investable_capital": investable_capital,
    }


def write_holdings_csv_from_db(supabase, portfolio_id: str) -> None:
    """
    Export current holdings from Supabase to ``trades/holdings.csv``.

    The C++ binary reads this file to determine existing positions before
    computing trade deltas.  Shares are cast to int because the C++
    parser expects whole numbers.

    Parameters
    ----------
    supabase : supabase.Client
        Initialised Supabase client.
    portfolio_id : str
        Portfolio UUID whose holdings to export.
    """
    response = (
        supabase.table("holdings")
        .select("*")
        .eq("portfolio_id", portfolio_id)
        .execute()
    )

    csv_path = os.path.join(PREDICTIONS_DIR, "holdings.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "shares", "avg_price", "last_updated"])
        for h in (response.data or []):
            writer.writerow([
                h["ticker"],
                int(h["quantity"]),          # DB stores float, C++ expects int
                h["average_buy_price"],
                h.get("updated_at", ""),
            ])


def apply_portfolio_csv_to_db(supabase, portfolio_id: str, csv_path: str | None = None) -> None:
    """
    Read a portfolio CSV and sync the results back into Supabase.

    Parameters
    ----------
    csv_path : str | None
        Path to the CSV file.  Defaults to ``trades/portfolio.csv``
        when None, which preserves existing C++ loop behaviour.  The
        news prediction loop passes ``trades/news_portfolio.csv``.

    For each row in the CSV:
      - **buy**  — upsert holding (insert or update qty + weighted avg
        price) and log a buy transaction.
      - **sell** — decrease holding qty (delete if ≤ 0) and log a sell
        transaction.
      - **hold** — log a hold transaction (no position change).
      - **CASH_RESERVE** — update ``portfolios.cash_reserve`` and
        recompute ``current_portfolio_value``.

    Parameters
    ----------
    supabase : supabase.Client
        Initialised Supabase client.
    portfolio_id : str
        Portfolio UUID to update.
    """
    # Default to the C++ output if no explicit path was given.
    if csv_path is None:
        csv_path = os.path.join(PREDICTIONS_DIR, "portfolio.csv")

    # Guard: skip if C++ didn't produce the file or it's empty.
    if not os.path.isfile(csv_path) or os.path.getsize(csv_path) == 0:
        print("[Prediction] WARNING: portfolio.csv missing or empty — skipping DB sync", flush=True)
        return

    rows: list[dict] = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    for row in rows:
        ticker = row["ticker"]
        action = row["action"].strip().lower()
        amount_of_shares = int(row["amount_of_shares"])
        total_change = float(row["total_change"])

        # ── CASH_RESERVE summary row ─────────────────────────────────
        if ticker == "CASH_RESERVE":
            # total_change is the post-trade cash balance from C++.
            supabase.table("portfolios").update({
                "cash_reserve": total_change,
            }).eq("portfolio_id", portfolio_id).execute()

            # Recompute current_portfolio_value = sum(qty * avg_price) + cash.
            holdings_resp = (
                supabase.table("holdings")
                .select("quantity, average_buy_price")
                .eq("portfolio_id", portfolio_id)
                .execute()
            )
            holdings_value = sum(
                float(h["quantity"]) * float(h["average_buy_price"])
                for h in (holdings_resp.data or [])
            )
            supabase.table("portfolios").update({
                "current_portfolio_value": holdings_value + total_change,
            }).eq("portfolio_id", portfolio_id).execute()
            continue

        # ── BUY action ───────────────────────────────────────────────
        if action == "buy":
            # Check for existing holding.
            existing = (
                supabase.table("holdings")
                .select("*")
                .eq("portfolio_id", portfolio_id)
                .eq("ticker", ticker)
                .execute()
            )

            if existing.data:
                # Update: increase quantity and recalculate weighted avg price.
                old = existing.data[0]
                old_qty = float(old["quantity"])
                old_avg = float(old["average_buy_price"])
                new_qty = float(amount_of_shares)
                price_per_share = abs(total_change / amount_of_shares) if amount_of_shares else 0
                # Weighted average: (old_qty*old_avg + new_qty*price) / (old_qty+new_qty)
                new_avg = (
                    (old_qty * old_avg + new_qty * price_per_share)
                    / (old_qty + new_qty)
                ) if (old_qty + new_qty) > 0 else 0

                supabase.table("holdings").update({
                    "quantity": old_qty + new_qty,
                    "average_buy_price": new_avg,
                }).eq("holding_id", old["holding_id"]).execute()
            else:
                # Insert new holding row.
                price_per_share = abs(total_change / amount_of_shares) if amount_of_shares else 0
                supabase.table("holdings").insert({
                    "portfolio_id": portfolio_id,
                    "ticker": ticker,
                    "quantity": float(amount_of_shares),
                    "average_buy_price": price_per_share,
                }).execute()

            # Log buy transaction.
            price_per_unit = abs(total_change / amount_of_shares) if amount_of_shares else 0
            supabase.table("transactions").insert({
                "portfolio_id": portfolio_id,
                "ticker": ticker,
                "tx_type": "BUY",
                "quantity": float(amount_of_shares),
                "price_per_unit": price_per_unit,
                "total_amount": abs(total_change),
            }).execute()

        # ── SELL action ──────────────────────────────────────────────
        elif action == "sell":
            existing = (
                supabase.table("holdings")
                .select("*")
                .eq("portfolio_id", portfolio_id)
                .eq("ticker", ticker)
                .execute()
            )

            if existing.data:
                old = existing.data[0]
                old_qty = float(old["quantity"])
                new_qty = old_qty - float(amount_of_shares)

                if new_qty <= 0:
                    # Position fully closed — delete the holding row.
                    supabase.table("holdings").delete().eq(
                        "holding_id", old["holding_id"]
                    ).execute()
                else:
                    # Partial sell — decrease quantity, keep avg price.
                    supabase.table("holdings").update({
                        "quantity": new_qty,
                    }).eq("holding_id", old["holding_id"]).execute()

            # Log sell transaction.
            price_per_unit = abs(total_change / amount_of_shares) if amount_of_shares else 0
            supabase.table("transactions").insert({
                "portfolio_id": portfolio_id,
                "ticker": ticker,
                "tx_type": "SELL",
                "quantity": float(amount_of_shares),
                "price_per_unit": price_per_unit,
                "total_amount": abs(total_change),
            }).execute()

        # ── HOLD action ──────────────────────────────────────────────
        elif action == "hold":
            # No position change — just record the hold in the transaction log.
            supabase.table("transactions").insert({
                "portfolio_id": portfolio_id,
                "ticker": ticker,
                "tx_type": "HOLD",
                "quantity": 0,
                "price_per_unit": 0,
                "total_amount": 0,
            }).execute()


# ── Stock tracking ────────────────────────────────────────────────────────────

async def _track_ticker(ticker: str) -> None:
    """
    Background task that back-fills ~2 days of 1-minute candle history
    from yfinance, then polls for the latest candle every
    POLL_INTERVAL_SECONDS and appends it to the ticker's CSV file.

    Parameters
    ----------
    ticker : str
        Uppercase ticker symbol (e.g. "AAPL").

    Runs until cancelled (via DELETE /track/{ticker} or shutdown).
    """
    os.makedirs(STOCK_DATA_DIR, exist_ok=True)
    csv_path = os.path.join(STOCK_DATA_DIR, f"{ticker}.csv")

    if not os.path.exists(csv_path):
        with open(csv_path, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp", "ticker", "current_price", "day_high", "day_low", "volume", "market_cap"])

    # ── Backlog ──────────────────────────────────────────────────────
    # Pre-populate the CSV so downstream consumers (charts, ML models)
    # have data to work with immediately instead of waiting for the
    # polling loop to accumulate rows one-by-one.
    # Uses explicit start/end so that TIME_REWIND_HOURS shifts the
    # window into the past (when 0, start/end match the real-time
    # "2d" window).
    loop = asyncio.get_running_loop()
    sim_now = _simulated_now()
    backlog_start = sim_now - timedelta(days=2)
    backlog_df = await loop.run_in_executor(
        None,
        lambda: yf.Ticker(ticker).history(start=backlog_start, end=sim_now, interval="1m"),
    )

    # Fetch market cap once as a snapshot; yfinance does not provide
    # historical market cap per candle so we reuse the current value.
    ticker_info = await loop.run_in_executor(None, lambda: yf.Ticker(ticker).info)
    market_cap = ticker_info.get("marketCap", "")

    if backlog_df is not None and not backlog_df.empty:
        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            for idx, row in backlog_df.iterrows():
                writer.writerow([
                    str(idx),   # pandas Timestamp -> string
                    ticker,
                    row["Close"],   # current_price mapped from Close
                    row["High"],    # day_high
                    row["Low"],     # day_low
                    row["Volume"],
                    market_cap,
                ])

    # ── Live polling loop ────────────────────────────────────────────
    try:
        while True:
            # yfinance is synchronous — offload to a thread so the
            # event loop stays responsive.
            # Recompute simulated now each cycle so the window stays
            # anchored to the rewound clock.
            loop = asyncio.get_running_loop()
            sim_now = _simulated_now()
            poll_start = sim_now - timedelta(days=1)
            df = await loop.run_in_executor(
                None,
                lambda: yf.Ticker(ticker).history(start=poll_start, end=sim_now, interval="1m"),
            )

            if df is not None and not df.empty:
                latest_candle = df.iloc[-1]
                candle_timestamp = str(df.index[-1])  # pandas Timestamp -> string

                # Re-fetch market cap each cycle so the snapshot stays
                # reasonably current.
                poll_ticker_info = await loop.run_in_executor(None, lambda: yf.Ticker(ticker).info)
                poll_market_cap = poll_ticker_info.get("marketCap", "")

                with open(csv_path, "a", newline="") as f:
                    csv.writer(f).writerow([
                        candle_timestamp,
                        ticker,
                        latest_candle["Close"],   # current_price
                        latest_candle["High"],    # day_high
                        latest_candle["Low"],     # day_low
                        latest_candle["Volume"],
                        poll_market_cap,
                    ])

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except asyncio.CancelledError:
        pass


# ── News tracking ─────────────────────────────────────────────────────────────

def _fetch_finnhub_news() -> list[dict]:
    """
    Synchronous helper that calls the Finnhub general-news API.

    Returns
    -------
    list[dict]
        Article dicts whose keys match NEWS_CSV_COLUMNS.
        Returns an empty list on any request failure.
    """
    try:
        resp = requests.get(
            FINNHUB_NEWS_URL,
            params={"category": "general", "token": FINNHUB_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


async def _track_news() -> None:
    """
    Background task that polls Finnhub for general market news every
    POLL_INTERVAL_SECONDS and appends new articles to data/news/news.csv.

    Articles are deduplicated by their Finnhub-assigned ``id`` so that
    repeated polling cycles never write the same article twice.

    Runs until cancelled (via DELETE /news or shutdown).
    """
    os.makedirs(NEWS_DIR, exist_ok=True)
    csv_path = os.path.join(NEWS_DIR, "news.csv")

    if not os.path.exists(csv_path):
        with open(csv_path, "w", newline="") as f:
            csv.writer(f).writerow(NEWS_CSV_COLUMNS)

    try:
        while True:
            # requests is synchronous — offload to a thread so the
            # event loop stays responsive.
            loop = asyncio.get_running_loop()
            articles = await loop.run_in_executor(None, _fetch_finnhub_news)

            # Filter out articles already seen AND articles published after
            # the simulated time. Finnhub's general-news API has no
            # server-side date-range param, so filtering is client-side.
            # When TIME_REWIND_HOURS=0, cutoff equals real now and every
            # returned article passes the timestamp check.
            sim_cutoff = _simulated_now().timestamp()
            new_articles = [
                a for a in articles
                if a.get("id") not in seen_news_ids
                and a.get("datetime", 0) <= sim_cutoff
            ]

            if new_articles:
                with open(csv_path, "a", newline="") as f:
                    writer = csv.writer(f)
                    for article in new_articles:
                        writer.writerow([
                            article.get("id", ""),
                            article.get("category", ""),
                            article.get("datetime", ""),
                            article.get("headline", ""),
                            article.get("source", ""),
                            article.get("summary", ""),
                            article.get("url", ""),
                            article.get("image", ""),
                            article.get("related", ""),
                        ])
                        seen_news_ids.add(article.get("id"))

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except asyncio.CancelledError:
        pass


# ── Prediction loop ───────────────────────────────────────────────────────────

async def _run_prediction_loop() -> None:
    """
    Background task that re-runs the C++ efficient-frontier predictor
    once per POLL_INTERVAL_SECONDS.

    Behaviour:
      - Waits one full POLL_INTERVAL_SECONDS before the first run so
        _track_ticker has already back-filled and written CSV rows.
      - Skips a cycle (with a printed warning) if no tickers are
        currently being tracked via POST /track/<ticker>.
      - Skips a cycle if the compiled binary cannot be found on disk.
      - Captures stdout/stderr from the subprocess and prints them so
        the Uvicorn terminal shows the full C++ prediction output.
      - Runs until cancelled by DELETE /predict or server shutdown.

    The C++ binary is invoked as:
        <PREDICTION_BIN> <STOCK_DATA_DIR> <PREDICTIONS_DIR> <total_capital> <investable_capital> TICKER1 TICKER2 ...
    """
    os.makedirs(PREDICTIONS_DIR, exist_ok=True)

    # Give the stock-tracking loop one full cycle head-start so CSVs
    # exist and have at least the backlog rows written before we run.
    await asyncio.sleep(POLL_INTERVAL_SECONDS)

    try:
        while True:
            # ── Guard: binary must be compiled and present ────────────
            if not os.path.isfile(PREDICTION_BIN):
                print(
                    f"[Prediction] WARNING: binary not found at {PREDICTION_BIN}.\n"
                    "  Compile with:\n"
                    "  g++ -O2 -std=c++17 -o backend/prediction/prediction "
                    "backend/prediction/prediction.cpp",
                    flush=True,
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── Guard: at least one ticker must be actively tracked ───
            tickers = list(stock_tasks.keys())
            if not tickers:
                print(
                    "[Prediction] WARNING: no tickers are being tracked — skipping cycle. "
                    "POST /track/<ticker> to start collecting data.",
                    flush=True,
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── Fetch portfolio state from Supabase ────────────────────
            # Pull current capital figures and write holdings.csv so the
            # C++ binary sees the latest DB positions.
            total_capital = 100000000.0       # fallback defaults
            investable_capital = 90000000.0
            try:
                supabase = get_supabase_client_direct()
                portfolio_state = fetch_portfolio_state(supabase)
                portfolio_id = portfolio_state["portfolio_id"]
                total_capital = portfolio_state["total_capital"]
                investable_capital = portfolio_state["investable_capital"]
                write_holdings_csv_from_db(supabase, portfolio_id)
                print(
                    f"[Prediction] DB sync: total_capital={total_capital:.2f}, "
                    f"investable_capital={investable_capital:.2f}",
                    flush=True,
                )
            except Exception as exc:
                # Non-fatal: log and continue with fallback capital values.
                print(
                    f"[Prediction] WARNING: could not fetch portfolio state "
                    f"from Supabase ({exc}) — using fallback capital values",
                    flush=True,
                )
                portfolio_id = None  # signals "skip DB write-back later"

            # ── Run the C++ predictor ─────────────────────────────────
            # Use subprocess.run in a thread executor rather than
            # asyncio.create_subprocess_exec — the async variant requires
            # ProactorEventLoop on Windows which uvicorn does not use,
            # causing silent failures. run_in_executor is cross-platform.
            cmd = [
                PREDICTION_BIN, STOCK_DATA_DIR, PREDICTIONS_DIR,
                str(total_capital), str(investable_capital),
            ] + tickers
            print(f"[Prediction] Running: {' '.join(cmd)}", flush=True)

            try:
                import subprocess as _subprocess

                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: _subprocess.run(
                        cmd,
                        capture_output=True,
                    ),
                )

                if result.stdout:
                    print(result.stdout.decode(errors="replace"), flush=True)

                if result.stderr:
                    print(
                        f"[Prediction] STDERR:\n{result.stderr.decode(errors='replace')}",
                        flush=True,
                    )

                if result.returncode != 0:
                    print(
                        f"[Prediction] WARNING: process exited with code {result.returncode}",
                        flush=True,
                    )
                else:
                    print(
                        f"[Prediction] Cycle complete — "
                        f"portfolio.csv updated in {PREDICTIONS_DIR}/",
                        flush=True,
                    )

                    # ── Write C++ results back to Supabase ────────────
                    # Only attempt if we successfully fetched portfolio
                    # state earlier (portfolio_id is not None).
                    if portfolio_id is not None:
                        try:
                            apply_portfolio_csv_to_db(supabase, portfolio_id)
                            print(
                                "[Prediction] DB sync: portfolio.csv applied to Supabase",
                                flush=True,
                            )
                        except Exception as db_exc:
                            print(
                                f"[Prediction] WARNING: failed to sync "
                                f"portfolio.csv to Supabase: {db_exc}",
                                flush=True,
                            )

            except Exception as exc:
                # Don't let a single failed run kill the loop.
                print(f"[Prediction] ERROR during subprocess: {exc}", flush=True)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except asyncio.CancelledError:
        print("[Prediction] Loop cancelled — stopping.", flush=True)


# ── News-sentiment prediction loop ──────────────────────────────────────────

async def _run_news_prediction_loop() -> None:
    """
    Background task that re-runs the Claude-based news-sentiment overlay
    every POLL_INTERVAL_SECONDS.

    Mirrors ``_run_prediction_loop()`` structure:
      - Initial wait of POLL_INTERVAL_SECONDS so news/stock data is ready.
      - Each cycle checks whether news.csv has changed since the last run;
        skips the (expensive) Claude call when news hasn't changed.
      - On success, writes trades/news_portfolio.csv and syncs results to
        Supabase via ``apply_portfolio_csv_to_db()``.
      - Runs until cancelled by DELETE /news/predict or server shutdown.
    """
    global _last_news_csv_mtime

    # Give tracking loops a head-start so CSVs exist.
    await asyncio.sleep(POLL_INTERVAL_SECONDS)

    try:
        while True:
            print("[News Prediction] Cycle starting...", flush=True)

            # ── Guard: news tracking must be active ──────────────────
            if news_task is None:
                print(
                    "[News Prediction] WARNING: news tracking is not active — "
                    "skipping cycle. POST /news first.",
                    flush=True,
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── Guard: at least one ticker must be tracked ───────────
            tickers = list(stock_tasks.keys())
            if not tickers:
                print(
                    "[News Prediction] WARNING: no tickers tracked — "
                    "skipping cycle.",
                    flush=True,
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── Guard: portfolio.csv must exist ──────────────────────
            portfolio_csv_path = os.path.join(PREDICTIONS_DIR, "portfolio.csv")
            if not os.path.isfile(portfolio_csv_path):
                print(
                    "[News Prediction] WARNING: trades/portfolio.csv not found — "
                    "waiting for C++ predictor to run first.",
                    flush=True,
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── Guard: Anthropic API key ─────────────────────────────
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                print(
                    "[News Prediction] WARNING: ANTHROPIC_API_KEY not set — "
                    "skipping cycle.",
                    flush=True,
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── News change detection ────────────────────────────────
            news_csv_path = os.path.join(NEWS_DIR, "news.csv")
            try:
                current_mtime = os.path.getmtime(news_csv_path)
            except OSError:
                print(
                    "[News Prediction] WARNING: news.csv not found — "
                    "skipping cycle.",
                    flush=True,
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            if current_mtime == _last_news_csv_mtime:
                print(
                    "[News Prediction] No new news since last cycle — skipping Claude call.",
                    flush=True,
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── Fetch portfolio state from Supabase ──────────────────
            total_capital = 100000000.0  # fallback default
            portfolio_id = None
            try:
                supabase = get_supabase_client_direct()
                portfolio_state = fetch_portfolio_state(supabase)
                portfolio_id = portfolio_state["portfolio_id"]
                total_capital = portfolio_state["total_capital"]
                write_holdings_csv_from_db(supabase, portfolio_id)
                print(
                    f"[News Prediction] DB sync: total_capital={total_capital:.2f}",
                    flush=True,
                )
            except Exception as exc:
                print(
                    f"[News Prediction] WARNING: could not fetch portfolio state "
                    f"from Supabase ({exc}) — using fallback capital",
                    flush=True,
                )

            # ── Load CSVs ────────────────────────────────────────────
            holdings_csv_path = os.path.join(PREDICTIONS_DIR, "holdings.csv")
            output_csv_path = os.path.join(PREDICTIONS_DIR, "news_portfolio.csv")

            try:
                news_data = load_news_csv(news_csv_path)
                portfolio_data = load_portfolio_csv(portfolio_csv_path)
                holdings_data = load_holdings_csv(holdings_csv_path)
            except Exception as exc:
                print(
                    f"[News Prediction] ERROR loading CSVs: {exc}",
                    flush=True,
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── Build prompt and call Claude ─────────────────────────
            prompt = build_prompt(
                portfolio=portfolio_data,
                holdings=holdings_data,
                news=news_data,
                total_capital=total_capital,
                tickers=tickers,
            )

            client = anthropic.Anthropic(api_key=api_key)
            loop = asyncio.get_running_loop()

            try:
                result = await loop.run_in_executor(
                    None, lambda: call_claude(prompt, client)
                )
            except ValueError as exc:
                print(
                    f"[News Prediction] ERROR: Claude returned invalid JSON: {exc}",
                    flush=True,
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── Validate response ────────────────────────────────────
            try:
                validate_response(result, total_capital)
            except ValueError as exc:
                print(
                    f"[News Prediction] ERROR: validation failed: {exc}",
                    flush=True,
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── Write adjusted trade plan ────────────────────────────
            write_portfolio_csv(result["trades"], output_csv_path)
            print(
                f"[News Prediction] Wrote adjusted trade plan → {output_csv_path}",
                flush=True,
            )

            # ── Sync to Supabase ─────────────────────────────────────
            if portfolio_id is not None:
                try:
                    apply_portfolio_csv_to_db(
                        supabase, portfolio_id, csv_path=output_csv_path
                    )
                    print(
                        "[News Prediction] DB sync: news_portfolio.csv applied to Supabase",
                        flush=True,
                    )
                except Exception as db_exc:
                    print(
                        f"[News Prediction] WARNING: failed to sync to Supabase: {db_exc}",
                        flush=True,
                    )

            # ── Update mtime tracker and print rationale ─────────────
            _last_news_csv_mtime = current_mtime
            print(
                f"[News Prediction] Rationale: {result.get('rationale', '(none)')}",
                flush=True,
            )
            print(
                f"[News Prediction] Cycle complete — "
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                flush=True,
            )

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except asyncio.CancelledError:
        print("[News Prediction] Loop cancelled — stopping.", flush=True)


# ── Stock endpoints ───────────────────────────────────────────────────────────

@app.get("/")
def health_check():
    """Simple health-check that confirms the server is running."""
    return {"status": "ok"}


@app.post("/track/{ticker}")
async def start_tracking(ticker: str):
    """
    Start tracking a stock ticker.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (case-insensitive; normalised to uppercase).

    Returns 200 on success or 409 if the ticker is already being tracked.
    """
    ticker = ticker.upper()

    if ticker in stock_tasks:
        raise HTTPException(status_code=409, detail=f"{ticker} is already being tracked")

    task = asyncio.create_task(_track_ticker(ticker))
    stock_tasks[ticker] = task

    return {"message": f"Started tracking {ticker}"}


@app.delete("/track/{ticker}")
async def stop_tracking(ticker: str):
    """
    Stop tracking a stock ticker.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (case-insensitive; normalised to uppercase).

    Returns 200 on success or 404 if the ticker is not currently tracked.
    """
    ticker = ticker.upper()

    if ticker not in stock_tasks:
        raise HTTPException(status_code=404, detail=f"{ticker} is not being tracked")

    stock_tasks[ticker].cancel()
    del stock_tasks[ticker]

    return {"message": f"Stopped tracking {ticker}"}


@app.get("/track")
def list_tracked():
    """
    Return the list of ticker symbols currently being tracked.

    Returns a JSON object with a single key "tracked" whose value is a
    sorted list of uppercase ticker strings.
    """
    return {"tracked": sorted(stock_tasks.keys())}


# ── News endpoints ────────────────────────────────────────────────────────────

@app.post("/news")
async def start_news_tracking():
    """
    Start tracking general market news from Finnhub.

    Launches a background task that polls the Finnhub general-news API
    every POLL_INTERVAL_SECONDS and appends new articles to news/news.csv.

    Returns 200 on success, 409 if news is already being tracked, or
    400 if the FINNHUB_API_KEY environment variable is not set.
    """
    global news_task

    if not FINNHUB_API_KEY or FINNHUB_API_KEY == "your_finnhub_api_key_here":
        raise HTTPException(
            status_code=400,
            detail="FINNHUB_API_KEY is not set — add it to backend/.env",
        )

    if news_task is not None:
        raise HTTPException(status_code=409, detail="News is already being tracked")

    news_task = asyncio.create_task(_track_news())

    return {"message": "Started tracking news"}


@app.delete("/news")
async def stop_news_tracking():
    """
    Stop tracking general market news.

    Cancels the running news-polling background task.

    Returns 200 on success or 404 if news tracking is not active.
    """
    global news_task

    if news_task is None:
        raise HTTPException(status_code=404, detail="News is not being tracked")

    news_task.cancel()
    news_task = None

    return {"message": "Stopped tracking news"}


# ── Prediction endpoints ──────────────────────────────────────────────────────

@app.post("/predict")
async def start_prediction():
    """
    Start the recurring prediction loop.

    Waits one full POLL_INTERVAL_SECONDS before the first run so stock
    CSVs have time to be populated, then re-runs the C++ efficient-frontier
    predictor every POLL_INTERVAL_SECONDS thereafter.

    Tickers are read dynamically from whatever is currently tracked via
    POST /track/<ticker> at the start of each cycle — adding or removing
    tickers takes effect on the next run without restarting this loop.

    Requires at least one ticker to be actively tracked (checked each
    cycle; skips with a warning if none are found).

    Writes each cycle:
      - trades/portfolio.csv  — trade actions (BUY / SELL / HOLD)
      - trades/holdings.csv   — updated position snapshot

    Returns 409 if the prediction loop is already running.
    """
    global prediction_task

    if prediction_task is not None:
        raise HTTPException(
            status_code=409,
            detail="Prediction loop is already running. DELETE /predict to stop it first.",
        )

    prediction_task = asyncio.create_task(_run_prediction_loop())

    return {
        "message": (
            f"Prediction loop started. "
            f"First run in ~{POLL_INTERVAL_SECONDS}s once stock data is ready. "
            f"Output will be written to {PREDICTIONS_DIR}/"
        )
    }


@app.delete("/predict")
async def stop_prediction():
    """
    Stop the recurring prediction loop.

    Returns 404 if the prediction loop is not currently running.
    """
    global prediction_task

    if prediction_task is None:
        raise HTTPException(
            status_code=404,
            detail="Prediction loop is not running. POST /predict to start it.",
        )

    prediction_task.cancel()
    prediction_task = None

    return {"message": "Prediction loop stopped."}


@app.get("/predict")
def prediction_status():
    """
    Return the current status of the prediction loop.

    Response fields:
      running         — bool, whether the loop is active
      binary          — absolute path the server will invoke
      binary_exists   — bool, whether that binary is compiled and on disk
      output_dir      — directory where portfolio.csv / holdings.csv are written
      poll_interval_s — seconds between prediction cycles
      tracked_tickers — tickers that will be passed on the next run
    """
    return {
        "running": prediction_task is not None,
        "binary": PREDICTION_BIN,
        "binary_exists": os.path.isfile(PREDICTION_BIN),
        "output_dir": PREDICTIONS_DIR,
        "poll_interval_s": POLL_INTERVAL_SECONDS,
        "tracked_tickers": sorted(stock_tasks.keys()),
    }


# ── News-sentiment prediction endpoints ───────────────────────────────────────

@app.post("/news/predict")
async def start_news_prediction():
    """
    Start the recurring news-sentiment prediction loop.

    Launches a background task that calls Claude every POLL_INTERVAL_SECONDS
    to adjust the C++ trade plan based on Finnhub news sentiment.  Skips
    the Claude call when news.csv hasn't changed since the last cycle.

    Returns 409 if the loop is already running.
    """
    global news_prediction_task

    if news_prediction_task is not None:
        raise HTTPException(
            status_code=409,
            detail="News prediction loop is already running. DELETE /news/predict to stop it first.",
        )

    news_prediction_task = asyncio.create_task(_run_news_prediction_loop())

    return {
        "message": (
            f"News prediction loop started. "
            f"First run in ~{POLL_INTERVAL_SECONDS}s once data is ready. "
            f"Output will be written to {PREDICTIONS_DIR}/news_portfolio.csv"
        )
    }


@app.delete("/news/predict")
async def stop_news_prediction():
    """
    Stop the recurring news-sentiment prediction loop.

    Returns 404 if the loop is not currently running.
    """
    global news_prediction_task

    if news_prediction_task is None:
        raise HTTPException(
            status_code=404,
            detail="News prediction loop is not running. POST /news/predict to start it.",
        )

    news_prediction_task.cancel()
    news_prediction_task = None

    return {"message": "News prediction loop stopped."}


# ── Database routers ──────────────────────────────────────────────────────────────
# Full CRUD for users, portfolios, holdings, and transactions tables.
# Each router lives in routers/ and uses Depends(get_supabase_client)
# from dependencies.py for the DB connection.
app.include_router(users_router.router)
app.include_router(portfolios_router.router)
app.include_router(holdings_router.router)
app.include_router(transactions_router.router)


# ── Validation error handler ───────────────────────────────────────────────────────
# Overrides FastAPI's default 422 response so the frontend always sees
# the same {"success": false, "error": "..."} shape on bad input.
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return validation errors in the standard error envelope."""
    return JSONResponse(
        status_code=400,
        content=error_response(str(exc.errors())),
    )


# ── Dashboard (React SPA) ─────────────────────────────────────────────────
# Serve index.html for all /dashboard/* paths so React Router handles
# client-side navigation (login, register, etc.).

@app.get("/dashboard/{full_path:path}")
@app.get("/dashboard")
async def serve_dashboard(full_path: str = ""):
    """
    Serve the React SPA for all /dashboard/* paths.

    If full_path points to an actual file on disk (e.g. assets/index-xxx.js),
    serve that file directly. Otherwise, serve index.html so React Router
    can handle the client-side route.
    """
    # Check if the path corresponds to a real static file (JS, CSS, images)
    file_path = os.path.join(_FRONTEND_DIST, full_path)
    if full_path and os.path.isfile(file_path):
        return FileResponse(file_path)
    # Fall back to index.html for SPA client-side routing
    return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"), media_type="text/html")


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Wipe all persisted data from previous runs so each server start is fresh."""
    for directory in (STOCK_DATA_DIR, NEWS_DIR):
        if os.path.exists(directory):
            shutil.rmtree(directory)
        os.makedirs(directory, exist_ok=True)

    # Ensure the trades output directory exists. Not wiped on restart
    # so holdings.csv survives across server restarts for trade continuity.
    os.makedirs(PREDICTIONS_DIR, exist_ok=True)

    if TIME_REWIND_HOURS > 0:
        print(
            f"[Canary AI] TIME_REWIND_HOURS={TIME_REWIND_HOURS} — "
            f"simulated time is {_simulated_now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )


@app.on_event("shutdown")
async def shutdown_event():
    """Cancel every running background task (stock + news + prediction + news prediction) on shutdown."""
    global news_task, prediction_task, news_prediction_task

    all_tasks = list(stock_tasks.values())

    for task in stock_tasks.values():
        task.cancel()

    if news_task is not None:
        news_task.cancel()
        all_tasks.append(news_task)
        news_task = None

    if prediction_task is not None:
        prediction_task.cancel()
        all_tasks.append(prediction_task)
        prediction_task = None

    if news_prediction_task is not None:
        news_prediction_task.cancel()
        all_tasks.append(news_prediction_task)
        news_prediction_task = None

    if all_tasks:
        await asyncio.gather(*all_tasks, return_exceptions=True)

    stock_tasks.clear()
    seen_news_ids.clear()


# ── Static file mount for built frontend assets (JS, CSS, images) ────────
# Must come after all route definitions. FastAPI checks explicit routes
# first; the mount only serves files that actually exist on disk.
# Only mounted if the frontend has been built (frontend/dist exists).
if os.path.isdir(_FRONTEND_DIST):
    app.mount("/dashboard", StaticFiles(directory=_FRONTEND_DIST), name="dashboard-static")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


