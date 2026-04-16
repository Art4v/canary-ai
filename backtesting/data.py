"""
data.py — Continuous minute-level stock data puller.

Polls yfinance every 60 seconds for a fixed set of tickers and appends
the latest 1-minute bar to a per-ticker CSV file in the `data/` directory.
The CSV schema matches exactly what prediction.cpp's load_csv() expects:

    timestamp,ticker,current_price,day_high,day_low,volume,market_cap

Time-rewind mode (set REWIND_HOURS in .env):
    When REWIND_HOURS > 0 the script treats (now - REWIND_HOURS) as the
    "current" moment and advances that simulated clock by 1 minute on every
    poll — replaying real historical bars so prediction.cpp can be tested
    while markets are closed.

Run with:
    python data.py

Press Ctrl+C to stop.
"""

import csv
import glob
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import yfinance as yf
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env (must happen before reading env vars)
# ---------------------------------------------------------------------------

# load_dotenv() reads the .env file sitting next to this script and populates
# os.environ. It is a no-op when the file doesn't exist.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Tickers to track — read from .env as a comma-separated list so both
# data.py and backtest.py share the same source of truth. Thinly traded /
# OTC symbols are fine: if yfinance returns no data for them in a given
# minute the script logs a warning and moves on without crashing.
TICKERS = [
    t.strip()
    for t in os.environ.get("TICKERS", "AAPL,TSLA,JPM,PLTR,CELS").split(",")
    if t.strip()
]

# Directory (relative to this script) where CSV files are written.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# How often to poll yfinance, in seconds.
INTERVAL_SECONDS = 60  # one full minute between pulls

# CSV column order — must match prediction.cpp:138 exactly.
CSV_HEADER = ["timestamp", "ticker", "current_price", "day_high", "day_low",
              "volume", "market_cap"]

# REWIND_HOURS — read from .env.
#   0        → live mode (default): always fetch the most recent bar.
#   positive → rewind mode: simulated clock starts at (now - REWIND_HOURS)
#              and advances 1 minute per poll.
#   float is supported, e.g. 6.5 = 6 hours 30 minutes.
try:
    REWIND_HOURS = float(os.environ.get("REWIND_HOURS", "0"))
except ValueError:
    REWIND_HOURS = 0.0  # fall back to live mode if the value is malformed

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clear_data_dir() -> None:
    """
    Delete all existing CSV files in DATA_DIR at startup.

    This ensures each run of data.py starts with a clean slate — no stale
    rows from a previous session can contaminate prediction.cpp's input.
    Only *.csv files are removed; other files (if any) are left untouched.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    for path in csv_files:
        os.remove(path)
        log.info("Cleared old data file: %s", path)
    if csv_files:
        log.info("Removed %d CSV file(s) from previous run.", len(csv_files))


def ensure_csv(path: str) -> None:
    """
    Create the CSV file with the header row if it does not already exist.

    Called before every append so that newly added tickers get a properly
    headed file on their first write without any manual setup.

    @param path  Absolute path to the CSV file for one ticker.
    """
    if not os.path.exists(path):
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(CSV_HEADER)
        log.info("Created %s", path)


def fetch_row_live(ticker: str) -> dict | None:
    """
    Fetch the latest completed 1-minute bar for `ticker` (live mode).

    Uses `period="1d"` to get all of today's intraday bars, then takes the
    last row. day_high, day_low, and market_cap come from `fast_info` — a
    single lightweight HTTP call rather than the heavy `.info` dict.

    Returns None when the DataFrame is empty (market closed / bad ticker)
    or when fast_info fields are unavailable.

    @param ticker  Stock symbol string, e.g. "AAPL".
    @return        Dict of field values ready to write, or None on failure.
    """
    tk = yf.Ticker(ticker)

    # period="1d" + interval="1m" gives all minute bars for the current session.
    hist = tk.history(period="1d", interval="1m")
    if hist.empty:
        log.warning("No 1-min data for %s (market closed or unknown ticker)", ticker)
        return None

    last = hist.iloc[-1]
    ts_index = hist.index[-1]

    # fast_info is a thin wrapper — much faster than .info for these three fields.
    fi = tk.fast_info
    day_high  = fi.day_high
    day_low   = fi.day_low
    market_cap = fi.market_cap

    # Treat any None/NaN from fast_info as a failed fetch — stod() in C++ would
    # crash on a non-numeric string.
    if day_high is None or day_low is None or market_cap is None:
        log.warning("Incomplete fast_info for %s — skipping this tick", ticker)
        return None

    # Timestamp: isoformat produces "2026-03-12T09:30:00-04:00"; replace T with
    # a space to match the format prediction.cpp's parse_timestamp() expects.
    timestamp_str = ts_index.isoformat().replace("T", " ")

    return {
        "timestamp":     timestamp_str,
        "ticker":        ticker,
        "current_price": float(last["Close"]),
        "day_high":      float(day_high),
        "day_low":       float(day_low),
        "volume":        float(last["Volume"]),
        "market_cap":    float(market_cap),
    }


def fetch_row_rewind(ticker: str, sim_time: datetime) -> dict | None:
    """
    Fetch the 1-minute bar for `ticker` at `sim_time` (rewind mode).

    Strategy:
      - Fetch all bars from the start of the simulated calendar day up to
        and including `sim_time` using explicit start/end parameters.
      - The last bar in that window is the "current" bar at sim_time.
      - day_high and day_low are computed as the running max/min over all
        bars in the window — this mirrors how fast_info works in live mode.
      - market_cap comes from fast_info (always reflects live market cap,
        which is an acceptable approximation for backtesting purposes).

    Returns None when no bars fall within the window.

    @param ticker    Stock symbol string, e.g. "AAPL".
    @param sim_time  The simulated "now" as a timezone-aware datetime.
    @return          Dict of field values ready to write, or None on failure.
    """
    tk = yf.Ticker(ticker)

    # Start of the simulated calendar day (midnight UTC).
    # yfinance interprets naive datetimes as UTC when used with start/end.
    sim_date_start = sim_time.replace(hour=0, minute=0, second=0, microsecond=0)

    # Add 1 minute to sim_time so the bar that starts exactly at sim_time
    # is included (yfinance's end parameter is exclusive).
    sim_end = sim_time + timedelta(minutes=1)

    hist = tk.history(start=sim_date_start, end=sim_end, interval="1m")
    if hist.empty:
        log.warning(
            "No historical data for %s at simulated time %s",
            ticker, sim_time.strftime("%Y-%m-%d %H:%M")
        )
        return None

    # Filter to bars whose timestamp is at or before sim_time.
    # yfinance bar timestamps mark the *start* of each 1-minute window.
    # Convert hist.index to UTC for a consistent comparison.
    hist_utc = hist.copy()
    hist_utc.index = hist_utc.index.tz_convert("UTC")
    bars_before = hist_utc[hist_utc.index <= sim_time]
    if bars_before.empty:
        log.warning("No bars before sim_time for %s", ticker)
        return None

    # Current bar = last bar in the window.
    bar      = bars_before.iloc[-1]
    ts_index = bars_before.index[-1]

    # Running intraday high/low: max High / min Low over all bars so far today.
    # Using the raw hist_utc slice so we cover the full day-to-sim_time window.
    day_high = float(bars_before["High"].max())
    day_low  = float(bars_before["Low"].min())

    # Market cap: fast_info always reflects the current live value.
    # For backtesting this is an acceptable approximation — the optimizer
    # uses it only as a relative weighting signal, not an absolute figure.
    fi = tk.fast_info
    market_cap = fi.market_cap
    if market_cap is None:
        log.warning("No market_cap for %s — skipping this tick", ticker)
        return None

    timestamp_str = ts_index.isoformat().replace("T", " ")

    return {
        "timestamp":     timestamp_str,
        "ticker":        ticker,
        "current_price": float(bar["Close"]),
        "day_high":      day_high,
        "day_low":       day_low,
        "volume":        float(bar["Volume"]),
        "market_cap":    float(market_cap),
    }


def append_row(row: dict, path: str) -> None:
    """
    Append one data row to the CSV file at `path`.

    Opens in append mode so existing rows are never overwritten.
    Fields are written in CSV_HEADER order to guarantee column alignment
    regardless of the dict's internal ordering.

    @param row   Dict produced by fetch_row_live / fetch_row_rewind.
    @param path  Absolute path to the target CSV file.
    """
    with open(path, "a", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([row[col] for col in CSV_HEADER])


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Entry point. Clears old CSVs, creates the data directory, then enters an
    infinite loop that polls every INTERVAL_SECONDS seconds.

    Live mode  (REWIND_HOURS == 0):
        Each iteration fetches the most recent 1-minute bar for every ticker.

    Rewind mode (REWIND_HOURS > 0):
        A simulated clock is initialised to (now - REWIND_HOURS) at startup.
        Each iteration fetches the historical bar nearest that simulated time,
        then advances the simulated clock by INTERVAL_SECONDS so successive
        polls replay consecutive minutes of market history.
    """
    # Wipe any CSV files left over from the previous run so prediction.cpp
    # always receives a clean, contiguous data set.
    clear_data_dir()

    log.info("Storing CSV files in: %s", DATA_DIR)
    log.info("Tracking tickers: %s", ", ".join(TICKERS))
    log.info("Poll interval: %d seconds — press Ctrl+C to stop", INTERVAL_SECONDS)

    if REWIND_HOURS > 0:
        # Simulated clock starts at (now - REWIND_HOURS) and advances each poll.
        # Use UTC throughout so yfinance comparisons are timezone-consistent.
        sim_time = datetime.now(tz=timezone.utc) - timedelta(hours=REWIND_HOURS)
        log.info(
            "REWIND MODE — simulated start time: %s UTC  (%.1f hours ago)",
            sim_time.strftime("%Y-%m-%d %H:%M"), REWIND_HOURS
        )
    else:
        sim_time = None  # unused in live mode
        log.info("LIVE MODE — fetching real-time data")

    while True:
        if sim_time is not None:
            log.info("--- polling (simulated time: %s UTC) ---",
                     sim_time.strftime("%Y-%m-%d %H:%M"))
        else:
            log.info("--- polling ---")

        for ticker in TICKERS:
            csv_path = os.path.join(DATA_DIR, f"{ticker}.csv")

            if sim_time is not None:
                # Rewind mode: fetch the bar at the simulated clock position.
                row = fetch_row_rewind(ticker, sim_time)
            else:
                # Live mode: fetch the most recently completed bar.
                row = fetch_row_live(ticker)

            if row is None:
                continue  # warning already logged inside fetch_row_*

            ensure_csv(csv_path)
            append_row(row, csv_path)
            log.info(
                "%-6s  price=%-10.4f  high=%-10.4f  low=%-10.4f  vol=%-12.0f  mcap=%.0f",
                ticker,
                row["current_price"],
                row["day_high"],
                row["day_low"],
                row["volume"],
                row["market_cap"],
            )

        # Advance the simulated clock by one poll interval so the next
        # iteration fetches the very next minute of historical data.
        if sim_time is not None:
            sim_time += timedelta(seconds=INTERVAL_SECONDS)

        # Sleep until the next polling interval.
        # INTERVAL_SECONDS is 60 — matching the "1m" yfinance bar width so
        # live mode never duplicates or skips a bar.
        log.info("Sleeping %d s until next poll…", INTERVAL_SECONDS)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Stopped by user.")
