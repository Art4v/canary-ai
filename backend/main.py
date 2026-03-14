"""
FastAPI backend for Canary AI.

Provides live stock-tracking endpoints (yfinance) and a general-news
tracking endpoint (Finnhub). Both data sources are polled every 10
seconds and persisted to CSV files that are wiped on every server startup.
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STOCK_DATA_DIR = os.path.join(DATA_DIR, "stock_training_data")
NEWS_DIR = os.path.join(DATA_DIR, "news")

PREDICTIONS_DIR = os.path.join(BASE_DIR, "predictions")
PREDICTION_EXE = os.path.join(BASE_DIR, "prediction", "prediction.exe")

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"

# Shared by both the stock and news polling loops.
POLL_INTERVAL_SECONDS = 60

# Shift the app's clock N hours into the past so yfinance returns data from
# that earlier window and Finnhub news is filtered to exclude articles
# published after the simulated time.  When 0 or unset, behaviour is
# identical to real-time.
TIME_REWIND_HOURS = float(os.getenv("TIME_REWIND_HOURS", "0"))

NEWS_CSV_COLUMNS = [
    "id", "category", "datetime", "headline",
    "source", "summary", "url", "image", "related",
]

# ── Time simulation ──────────────────────────────────────────────────────────

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

# Background task running the C++ prediction loop.
prediction_task: asyncio.Task | None = None

# Per-ticker events set after each data write; the prediction loop
# waits for ALL events before running the C++ prediction executable.
stock_data_events: dict[str, asyncio.Event] = {}

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
                    str(idx),   # pandas Timestamp → string
                    ticker,
                    row["Close"],   # current_price mapped from Close
                    row["High"],    # day_high
                    row["Low"],     # day_low
                    row["Volume"],
                    market_cap,
                ])

    # Signal that backlog data is available for prediction
    if ticker in stock_data_events:
        stock_data_events[ticker].set()

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
                candle_timestamp = str(df.index[-1])  # pandas Timestamp → string

                # Re-fetch market cap each cycle so the snapshot stays
                # reasonably current.  One extra API call per 60 s is
                # acceptable given the poll interval.
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

            # Signal that fresh data is available for prediction
            if ticker in stock_data_events:
                stock_data_events[ticker].set()

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
            # the simulated time.  Finnhub's general-news API has no
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

    # Create a data-ready event so the prediction loop can wait for this ticker
    stock_data_events[ticker] = asyncio.Event()

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

    # Set the event (to unblock any waiting prediction loop) then remove it
    if ticker in stock_data_events:
        stock_data_events[ticker].set()
        del stock_data_events[ticker]

    return {"message": f"Stopped tracking {ticker}"}


@app.get("/track")
def list_tracked():
    """
    Return the list of ticker symbols currently being tracked.

    Returns a JSON object with a single key "tracked" whose value is a
    sorted list of uppercase ticker strings.
    """
    return {"tracked": sorted(stock_tasks.keys())}


# ── Prediction loop ───────────────────────────────────────────────────────────

async def _run_prediction_loop() -> None:
    """
    Background task that waits for all tracked stocks to have fresh data,
    then runs the C++ prediction executable. Repeats until cancelled or
    no stocks remain.

    Each cycle re-snapshots current tickers so newly added/removed stocks
    are picked up automatically.
    """
    try:
        while True:
            # Snapshot current tickers from active tracking tasks
            current_tickers = list(stock_tasks.keys())

            # Auto-stop if no stocks are being tracked
            if not current_tickers:
                print("[Canary AI] Prediction loop: no stocks tracked, stopping.")
                break

            # Ensure events exist for all current tickers (handles newly added ones)
            for ticker in current_tickers:
                if ticker not in stock_data_events:
                    stock_data_events[ticker] = asyncio.Event()

            # Wait for ALL tracked tickers to signal fresh data
            await asyncio.gather(
                *(stock_data_events[t].wait() for t in current_tickers
                  if t in stock_data_events)
            )

            # Clear all events so the next cycle waits for new data
            for ticker in current_tickers:
                if ticker in stock_data_events:
                    stock_data_events[ticker].clear()

            # Build command: prediction.exe <data_dir> <output_dir> <TICKER1> ...
            cmd = [PREDICTION_EXE, STOCK_DATA_DIR, PREDICTIONS_DIR] + current_tickers
            print(f"[Canary AI] Running prediction: {' '.join(cmd)}")

            # Run the C++ executable as a subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            # Log the result
            if proc.returncode == 0:
                print(f"[Canary AI] Prediction completed successfully.")
                if stdout:
                    print(stdout.decode())
            else:
                print(f"[Canary AI] Prediction failed (exit code {proc.returncode}).")
                if stderr:
                    print(stderr.decode())

    except asyncio.CancelledError:
        pass


# ── Prediction endpoints ─────────────────────────────────────────────────────

@app.post("/predict")
async def start_prediction():
    """
    Start the background prediction loop.

    The loop waits for all tracked stocks to have fresh data, then runs
    the C++ prediction executable. Results are written to
    backend/predictions/portfolio.csv.

    Returns 200 on success, 409 if prediction is already running, or
    400 if no stocks are currently being tracked.
    """
    global prediction_task

    if prediction_task is not None and not prediction_task.done():
        raise HTTPException(status_code=409, detail="Prediction is already running")

    if not stock_tasks:
        raise HTTPException(status_code=400, detail="No stocks are being tracked")

    prediction_task = asyncio.create_task(_run_prediction_loop())

    return {"message": "Started prediction loop"}


@app.delete("/predict")
async def stop_prediction():
    """
    Stop the background prediction loop.

    Returns 200 on success or 404 if prediction is not running.
    """
    global prediction_task

    if prediction_task is None or prediction_task.done():
        raise HTTPException(status_code=404, detail="Prediction is not running")

    prediction_task.cancel()
    prediction_task = None

    return {"message": "Stopped prediction loop"}


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


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Wipe stock/news data from previous runs; preserve predictions across restarts."""
    for directory in (STOCK_DATA_DIR, NEWS_DIR):
        if os.path.exists(directory):
            shutil.rmtree(directory)
        os.makedirs(directory, exist_ok=True)

    # Predictions directory persists across restarts (holdings state matters)
    os.makedirs(PREDICTIONS_DIR, exist_ok=True)

    # Log the simulated time so operators can confirm the rewind is active.
    if TIME_REWIND_HOURS > 0:
        print(
            f"[Canary AI] TIME_REWIND_HOURS={TIME_REWIND_HOURS} — "
            f"simulated time is {_simulated_now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )


@app.on_event("shutdown")
async def shutdown_event():
    """Cancel every running background task (stock + news + prediction) on shutdown."""
    global news_task, prediction_task

    for task in stock_tasks.values():
        task.cancel()

    all_tasks = list(stock_tasks.values())
    if news_task is not None:
        news_task.cancel()
        all_tasks.append(news_task)
        news_task = None

    # Cancel prediction loop if running
    if prediction_task is not None and not prediction_task.done():
        prediction_task.cancel()
        all_tasks.append(prediction_task)
        prediction_task = None

    # Await cancellation so tasks can run their CancelledError handlers.
    if all_tasks:
        await asyncio.gather(*all_tasks, return_exceptions=True)
    stock_tasks.clear()
    stock_data_events.clear()
    seen_news_ids.clear()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
