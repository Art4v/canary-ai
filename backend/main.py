"""
FastAPI backend for Canary AI.

Provides live stock-tracking endpoints (yfinance), a general-news
tracking endpoint (Finnhub), and a prediction loop that runs the
compiled C++ efficient-frontier optimizer on demand.

All data sources are polled every POLL_INTERVAL_SECONDS and persisted
to CSV files that are wiped on every server startup.
"""

from fastapi import FastAPI, HTTPException
from datetime import datetime, timedelta, timezone
import yfinance as yf
import asyncio
import csv
import os
import shutil
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

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

# Tracks Finnhub article IDs already persisted so duplicate articles
# across polling cycles are never written twice.
seen_news_ids: set[int] = set()


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
        <PREDICTION_BIN> <STOCK_DATA_DIR> <PREDICTIONS_DIR> TICKER1 TICKER2 ...
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

            # ── Run the C++ predictor ─────────────────────────────────
            # Use subprocess.run in a thread executor rather than
            # asyncio.create_subprocess_exec — the async variant requires
            # ProactorEventLoop on Windows which uvicorn does not use,
            # causing silent failures. run_in_executor is cross-platform.
            cmd = [PREDICTION_BIN, STOCK_DATA_DIR, PREDICTIONS_DIR] + tickers
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

            except Exception as exc:
                # Don't let a single failed run kill the loop.
                print(f"[Prediction] ERROR during subprocess: {exc}", flush=True)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except asyncio.CancelledError:
        print("[Prediction] Loop cancelled — stopping.", flush=True)


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
    """Cancel every running background task (stock + news + prediction) on shutdown."""
    global news_task, prediction_task

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

    if all_tasks:
        await asyncio.gather(*all_tasks, return_exceptions=True)

    stock_tasks.clear()
    seen_news_ids.clear()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


