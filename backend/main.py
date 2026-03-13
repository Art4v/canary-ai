"""
FastAPI backend for Canary AI.

Provides a health-check endpoint and live stock-tracking endpoints.
Stock data is fetched via yfinance every 60 seconds and persisted
to per-ticker CSV files in the "stock_training_data/" directory.
The data directory is wiped on every server startup.
"""

from fastapi import FastAPI, HTTPException
import yfinance as yf
import asyncio
import csv
import os
import shutil
from datetime import datetime

app = FastAPI()

# ── State ────────────────────────────────────────────────────────────────────
# Maps uppercase ticker symbol → running asyncio.Task that periodically
# fetches data from yfinance and appends it to the ticker's CSV file.
tracking_tasks: dict[str, asyncio.Task] = {}

# Directory where per-ticker CSV files are stored.
# Located alongside this file: backend/stock_training_data/
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock_training_data")


# ── Background task ─────────────────────────────────────────────────────────

async def _track_ticker(ticker: str) -> None:
    """
    Long-running async task that fetches the latest 1-minute candle for
    *ticker* every 60 seconds and appends it to a CSV file.

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


# ── Lifecycle ────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Wipe all CSV data from previous runs so each server start is fresh."""
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    os.makedirs(DATA_DIR, exist_ok=True)


@app.on_event("shutdown")
async def shutdown_event():
    """Cancel every running tracking task when the server shuts down."""
    for ticker, task in tracking_tasks.items():
        task.cancel()
    # Wait for all tasks to finish their cancellation handling.
    if tracking_tasks:
        await asyncio.gather(*tracking_tasks.values(), return_exceptions=True)
    tracking_tasks.clear()


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
