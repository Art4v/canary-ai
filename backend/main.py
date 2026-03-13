"""
FastAPI backend for Canary AI.

Provides a health-check endpoint, live stock-tracking endpoints, and
a general-news tracking endpoint powered by Finnhub.
Stock data is fetched via yfinance every 10 seconds and persisted
to per-ticker CSV files in the "stock_training_data/" directory.
News articles are fetched via the Finnhub REST API every 10 seconds
and appended to "news/news.csv".
Both data directories are wiped on every server startup.
"""

from fastapi import FastAPI, HTTPException
import yfinance as yf
import asyncio
import csv
import os
import shutil
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env (contains FINNHUB_API_KEY).
load_dotenv()

app = FastAPI()

# ── State ────────────────────────────────────────────────────────────────────
# Maps uppercase ticker symbol → running asyncio.Task that periodically
# fetches data from yfinance and appends it to the ticker's CSV file.
tracking_tasks: dict[str, asyncio.Task] = {}

# Directory where per-ticker CSV files are stored.
# Located alongside this file: backend/stock_training_data/
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock_training_data")

# Directory where the general news CSV is stored.
NEWS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news")

# Finnhub API key loaded from .env — required for the /news endpoints.
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

# Base URL for the Finnhub general news endpoint.
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"

# The background task for news tracking (None when not tracking).
news_task: asyncio.Task | None = None

# Set of Finnhub article IDs already written to the CSV, used to
# deduplicate across polling cycles so the same article isn't stored twice.
seen_news_ids: set[int] = set()

# Column headers for news.csv — mirrors the fields returned by
# Finnhub's /news endpoint.
NEWS_CSV_COLUMNS = [
    "id", "category", "datetime", "headline",
    "source", "summary", "url", "image", "related",
]


# ── Background task ─────────────────────────────────────────────────────────

async def _track_ticker(ticker: str) -> None:
    """
    Long-running async task that fetches the latest 1-minute candle for
    *ticker* every 10 seconds and appends it to a CSV file.

    On first invocation the CSV is back-filled with ~2 days of 1-minute
    historical candles so that downstream consumers have immediate data.
    After the backfill, the function enters a polling loop that appends
    the most recent candle every 10 seconds.

    Parameters
    ----------
    ticker : str
        Uppercase ticker symbol (e.g. "AAPL").

    The task runs until cancelled (via DELETE /track/{ticker} or shutdown).
    """
    # Ensure the data directory exists (no-op if already present).
    os.makedirs(DATA_DIR, exist_ok=True)

    csv_path = os.path.join(DATA_DIR, f"{ticker}.csv")

    # If the CSV doesn't exist yet, create it with a header row.
    if not os.path.exists(csv_path):
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])

    # ── Backlog: pre-populate with 2 days of 1-minute historical candles ──
    # This gives the CSV an immediate history so downstream consumers
    # (charts, ML models, etc.) have data to work with right away,
    # instead of waiting for the 10-second polling loop to accumulate rows.
    loop = asyncio.get_running_loop()
    backlog_df = await loop.run_in_executor(
        None,
        lambda: yf.Ticker(ticker).history(period="2d", interval="1m"),
    )

    if backlog_df is not None and not backlog_df.empty:
        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            # Write every historical row — each row is one 1-minute candle.
            for idx, row in backlog_df.iterrows():
                writer.writerow([
                    str(idx),       # pandas Timestamp → string
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row["Volume"],
                ])

    # ── Live polling loop ──────────────────────────────────────────────
    try:
        while True:
            # yfinance is synchronous — run it in a thread executor so we
            # don't block the event loop while the HTTP request completes.
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(
                None,
                lambda: yf.Ticker(ticker).history(period="1d", interval="1m"),
            )

            # If the DataFrame has data, take the most recent candle and
            # append it as a new row in the CSV.
            if df is not None and not df.empty:
                last = df.iloc[-1]  # most recent 1-min candle
                candle_timestamp = str(df.index[-1])  # pandas Timestamp → str

                with open(csv_path, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        candle_timestamp,
                        last["Open"],
                        last["High"],
                        last["Low"],
                        last["Close"],
                        last["Volume"],
                    ])

            # Wait 10 seconds before fetching again.
            await asyncio.sleep(10)

    except asyncio.CancelledError:
        # Graceful exit when the task is cancelled (DELETE or shutdown).
        pass


# ── News background task ───────────────────────────────────────────────────

def _fetch_finnhub_news() -> list[dict]:
    """
    Synchronous helper that calls the Finnhub general-news API.

    Returns
    -------
    list[dict]
        A list of article dicts, each containing the keys listed in
        NEWS_CSV_COLUMNS. Returns an empty list on any request failure.
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
    Long-running async task that polls Finnhub for general market news
    every 10 seconds and appends new articles to news/news.csv.

    Each article is deduplicated by its Finnhub-assigned ``id`` so that
    repeated polling cycles never write the same article twice.

    The task runs until cancelled (via DELETE /news or shutdown).
    """
    global seen_news_ids

    # Ensure the news directory and CSV exist.
    os.makedirs(NEWS_DIR, exist_ok=True)
    csv_path = os.path.join(NEWS_DIR, "news.csv")

    # Create the CSV with a header row if it doesn't already exist.
    if not os.path.exists(csv_path):
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(NEWS_CSV_COLUMNS)

    try:
        while True:
            # requests is synchronous — run in a thread executor to
            # avoid blocking the event loop.
            loop = asyncio.get_running_loop()
            articles = await loop.run_in_executor(None, _fetch_finnhub_news)

            # Filter out articles we've already written.
            new_articles = [a for a in articles if a.get("id") not in seen_news_ids]

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
                        # Mark this article as seen so future cycles skip it.
                        seen_news_ids.add(article.get("id"))

            # Wait 10 seconds before polling again.
            await asyncio.sleep(10)

    except asyncio.CancelledError:
        # Graceful exit when the task is cancelled.
        pass


# ── Endpoints ────────────────────────────────────────────────────────────────

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
        Stock ticker symbol (case-insensitive; normalized to uppercase).

    Returns 200 on success or 409 if the ticker is already being tracked.
    """
    ticker = ticker.upper()

    if ticker in tracking_tasks:
        raise HTTPException(status_code=409, detail=f"{ticker} is already being tracked")

    # Spawn a background asyncio task that will run until cancelled.
    task = asyncio.create_task(_track_ticker(ticker))
    tracking_tasks[ticker] = task

    return {"message": f"Started tracking {ticker}"}


@app.delete("/track/{ticker}")
async def stop_tracking(ticker: str):
    """
    Stop tracking a stock ticker.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (case-insensitive; normalized to uppercase).

    Returns 200 on success or 404 if the ticker is not currently tracked.
    """
    ticker = ticker.upper()

    if ticker not in tracking_tasks:
        raise HTTPException(status_code=404, detail=f"{ticker} is not being tracked")

    # Cancel the running background task and remove it from state.
    tracking_tasks[ticker].cancel()
    del tracking_tasks[ticker]

    return {"message": f"Stopped tracking {ticker}"}


@app.get("/track")
def list_tracked():
    """
    Return the list of ticker symbols currently being tracked.

    Returns a JSON object with a single key "tracked" whose value is a
    sorted list of uppercase ticker strings.
    """
    return {"tracked": sorted(tracking_tasks.keys())}


# ── News endpoints ────────────────────────────────────────────────────────────

@app.post("/news")
async def start_news_tracking():
    """
    Start tracking general market news from Finnhub.

    Launches a background task that polls the Finnhub general-news API
    every 10 seconds and appends new articles to news/news.csv.

    Returns 200 on success, 409 if news is already being tracked, or
    400 if the FINNHUB_API_KEY environment variable is not set.
    """
    global news_task

    # Guard: make sure an API key is configured.
    if not FINNHUB_API_KEY or FINNHUB_API_KEY == "your_finnhub_api_key_here":
        raise HTTPException(
            status_code=400,
            detail="FINNHUB_API_KEY is not set — add it to backend/.env",
        )

    if news_task is not None:
        raise HTTPException(status_code=409, detail="News is already being tracked")

    # Spawn the background task.
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

    # Cancel the task and clear state.
    news_task.cancel()
    news_task = None

    return {"message": "Stopped tracking news"}


# ── Lifecycle ────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Wipe all stock and news data from previous runs so each server start is fresh."""
    # Wipe and recreate the stock data directory.
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    os.makedirs(DATA_DIR, exist_ok=True)

    # Wipe and recreate the news data directory.
    if os.path.exists(NEWS_DIR):
        shutil.rmtree(NEWS_DIR)
    os.makedirs(NEWS_DIR, exist_ok=True)


@app.on_event("shutdown")
async def shutdown_event():
    """Cancel every running tracking task (stock + news) when the server shuts down."""
    global news_task

    # Cancel all stock-tracking tasks.
    for ticker, task in tracking_tasks.items():
        task.cancel()

    # Cancel the news-tracking task if it's running.
    all_tasks = list(tracking_tasks.values())
    if news_task is not None:
        news_task.cancel()
        all_tasks.append(news_task)
        news_task = None

    # Wait for all tasks to finish their cancellation handling.
    if all_tasks:
        await asyncio.gather(*all_tasks, return_exceptions=True)
    tracking_tasks.clear()
    seen_news_ids.clear()


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
