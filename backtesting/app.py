"""
app.py — Continuous minute-level stock data puller.

Polls yfinance every 60 seconds for a fixed set of tickers and appends
the latest 1-minute bar to a per-ticker CSV file in the `data/` directory.
The CSV schema matches exactly what prediction.cpp's load_csv() expects:

    timestamp,ticker,current_price,day_high,day_low,volume,market_cap

Run with:
    python app.py

Press Ctrl+C to stop.
"""

import csv
import logging
import os
import time

import yfinance as yf

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Tickers to track. BOBS, KOD, ZIMV are thinly traded / OTC — if yfinance
# returns no data for them in a given minute the script logs a warning and
# moves on without crashing.
TICKERS = ["AAPL", "TSLA", "BOBS", "JPM", "PLTR", "CELS", "KOD", "ZIMV"]

# Directory (relative to this script) where CSV files are written.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# How often to poll yfinance, in seconds.
INTERVAL_SECONDS = 60  # one full minute between pulls

# CSV column order — must match prediction.cpp:138 exactly.
CSV_HEADER = ["timestamp", "ticker", "current_price", "day_high", "day_low",
              "volume", "market_cap"]

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

def ensure_csv(path: str) -> None:
    """
    Create the CSV file with the header row if it does not already exist.

    This is called before every append so that newly added tickers get a
    properly headed file on their first write without any manual setup.

    @param path  Absolute path to the CSV file for one ticker.
    """
    if not os.path.exists(path):
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(CSV_HEADER)
        log.info("Created %s", path)


def fetch_row(ticker: str) -> dict | None:
    """
    Fetch the latest completed 1-minute bar for `ticker` from yfinance.

    Strategy:
      - `history(period="1d", interval="1m")` returns all intraday bars for
        today as a DataFrame indexed by datetime.
      - We take the *last* row, which is the most recently completed bar.
      - day_high, day_low, and market_cap come from `fast_info` because it
        is a single lightweight HTTP call rather than the heavy `.info` dict.

    Returns a dict with keys matching CSV_HEADER, or None if:
      - The ticker returned an empty DataFrame (market closed / unknown symbol)
      - fast_info attributes are unavailable (NaN / None)

    @param ticker  Stock symbol string, e.g. "AAPL".
    @return        Dict of field values ready to write, or None on failure.
    """
    try:
        tk = yf.Ticker(ticker)

        # Fetch today's 1-minute bars. `period="1d"` covers the current
        # trading session; `interval="1m"` gives per-minute granularity.
        hist = tk.history(period="1d", interval="1m")

        if hist.empty:
            log.warning("No 1-min data for %s (market closed or unknown ticker)", ticker)
            return None

        # The last row is the most recent complete bar.
        last = hist.iloc[-1]

        # Timestamp: convert the pandas Timestamp index entry to a string
        # that matches the format prediction.cpp's parse_timestamp() expects:
        # "YYYY-MM-DD HH:MM:SS±HH:MM"
        ts_index = hist.index[-1]
        # pandas Timestamp.isoformat() produces "2026-03-12T09:30:00-04:00";
        # replace the 'T' separator with a space to match the C++ parser.
        timestamp_str = str(ts_index.isoformat()).replace("T", " ")

        # fast_info is a thin wrapper that avoids downloading the full info
        # dict — significantly fewer HTTP calls under the hood.
        fi = tk.fast_info

        # day_high / day_low from fast_info reflect the intraday range up to
        # this moment, which is what prediction.cpp treats them as.
        day_high = fi.day_high
        day_low = fi.day_low
        market_cap = fi.market_cap

        # Treat missing fast_info values as a failed fetch rather than
        # writing NaN/None into the CSV, which would break stod() in C++.
        if day_high is None or day_low is None or market_cap is None:
            log.warning("Incomplete fast_info for %s — skipping this tick", ticker)
            return None

        return {
            "timestamp":     timestamp_str,
            "ticker":        ticker,
            "current_price": float(last["Close"]),
            "day_high":      float(day_high),
            "day_low":       float(day_low),
            "volume":        float(last["Volume"]),   # cumulative vol for the bar
            "market_cap":    float(market_cap),
        }

    except Exception as exc:  # noqa: BLE001 — catch-all so one bad ticker can't kill the loop
        log.error("Error fetching %s: %s", ticker, exc)
        return None


def append_row(row: dict, path: str) -> None:
    """
    Append one data row to the CSV file at `path`.

    Opens in append mode so existing rows are never overwritten.
    Fields are written in CSV_HEADER order to guarantee column alignment.

    @param row   Dict produced by fetch_row(), keys match CSV_HEADER.
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
    Entry point. Creates the data directory, then enters an infinite loop
    that polls every INTERVAL_SECONDS seconds.

    Each iteration:
      1. Iterates over all configured tickers.
      2. Fetches the latest 1-minute bar via yfinance.
      3. Writes it to data/<TICKER>.csv (creating the file+header if needed).
    """
    # Create the data directory if it doesn't exist yet.
    os.makedirs(DATA_DIR, exist_ok=True)
    log.info("Storing CSV files in: %s", DATA_DIR)
    log.info("Tracking tickers: %s", ", ".join(TICKERS))
    log.info("Poll interval: %d seconds — press Ctrl+C to stop", INTERVAL_SECONDS)

    while True:
        log.info("--- polling ---")

        for ticker in TICKERS:
            csv_path = os.path.join(DATA_DIR, f"{ticker}.csv")

            row = fetch_row(ticker)
            if row is None:
                # Warning already logged inside fetch_row.
                continue

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

        # Sleep until the next polling interval.
        # INTERVAL_SECONDS is 60 — one bar per minute, matching the "1m"
        # yfinance interval so we never duplicate or miss a bar.
        log.info("Sleeping %d s until next poll…", INTERVAL_SECONDS)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Stopped by user.")
