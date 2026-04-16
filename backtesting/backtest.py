"""
backtest.py — Autonomous backtester for prediction.exe.

Glue layer that turns prediction.cpp's stateless optimizer into a full
trading simulator:

  1. Launches data.py as a subprocess so fresh CSVs land in data/
     (must be run in rewind mode — REWIND_HOURS > 0 in .env).
  2. Every 60 seconds calls prediction.exe with the current NAV and the
     list of tickers that actually have data, then parses portfolio.csv.
  3. Applies a realistic transaction-cost model:
         fee = max($5, 1.5% * trade notional)
     and a profitability gate:
         * buys always execute if cash allows
         * sells execute only if realised P&L > fee (avg-cost basis)
  4. Maintains in-memory portfolio state (cash / holdings / trade log),
     persists it to state.json every cycle, and rewrites the predictor's
     input holdings.csv so its next call is consistent with what we
     actually executed.
  5. Serves a barebones HTML UI on http://localhost:8787/ that polls
     /api/state every two seconds. Any browser can watch the run live.

Run with:  python backtest.py
Stop with: Ctrl+C (gracefully terminates data.py subprocess).
"""

import csv
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths & configuration
# ---------------------------------------------------------------------------

# Resolve everything relative to this file so the script works from any CWD.
BACKTEST_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(BACKTEST_DIR, "data")
TRADES_DIR   = os.path.join(BACKTEST_DIR, "trades")
STATE_FILE   = os.path.join(BACKTEST_DIR, "state.json")
UI_HTML      = os.path.join(BACKTEST_DIR, "backtest_ui.html")
DATA_PY      = os.path.join(BACKTEST_DIR, "data.py")

# prediction.exe on Windows, plain ./prediction elsewhere (best-effort).
PREDICTION_EXE = os.path.join(
    BACKTEST_DIR,
    "prediction.exe" if os.name == "nt" else "prediction",
)

# Tickers to track — read from .env as a comma-separated list so both
# backtest.py and data.py share the same source of truth. Falls back to a
# sensible default if the variable is absent.
TICKERS = [
    t.strip()
    for t in os.environ.get("TICKERS", "AAPL,TSLA,JPM,PLTR,CELS").split(",")
    if t.strip()
]

# Starting portfolio cash — configurable via .env so different capital
# scenarios can be tested without editing code.
try:
    INITIAL_CASH = float(os.environ.get("INITIAL_CASH", "1000"))
except ValueError:
    INITIAL_CASH = 1_000.00

# Fee model: max of a $5 floor or 1.5% of notional (user-specified).
FEE_MIN = 5.00
FEE_PCT = 0.015

# One cycle per minute — matches data.py's poll cadence so we run exactly
# once per new minute bar.
CYCLE_SECONDS = 60

# Bind the UI to loopback only — this is a single-user backtester, not a
# public service. Port chosen to be memorable and out of the common range.
HTTP_HOST = "127.0.0.1"
HTTP_PORT = 8787

# Load REWIND_HOURS from .env — we require rewind mode (>0).
load_dotenv(os.path.join(BACKTEST_DIR, ".env"))
try:
    REWIND_HOURS = float(os.environ.get("REWIND_HOURS", "0") or "0")
except ValueError:
    REWIND_HOURS = 0.0

# TIME_SPEED — simulation speed multiplier (rewind mode only).
#   1  → real-time replay (default), 10 → 10x faster, etc.
#   Ignored in live mode so the cycle cadence stays locked to 60 s.
try:
    _raw_speed = float(os.environ.get("TIME_SPEED", "1"))
    TIME_SPEED = max(1.0, _raw_speed)  # clamp: must be at least 1x
except ValueError:
    TIME_SPEED = 1.0

# In live mode, force 1x regardless of what .env says.
if REWIND_HOURS <= 0:
    TIME_SPEED = 1.0

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backtest")

# ---------------------------------------------------------------------------
# Shared state (guarded by state_lock)
# ---------------------------------------------------------------------------

# state_lock protects every read/write to the `state` dict. The HTTP server
# runs on a separate thread and must see a consistent snapshot, so we hold
# the lock while building its JSON response.
state_lock = threading.Lock()

# `state` is the single source of truth for portfolio / history / metrics.
# Values:
#   cash              — uninvested USD
#   nav               — cash + mark-to-market of all holdings
#   initial_cash      — for total-P&L display in the UI
#   holdings          — dict[ticker] -> {shares, avg_buy, last_price,
#                                        market_value, unrealized_pnl}
#   trades            — list of executed trades (chronological, unbounded)
#   trades_skipped    — count of sells skipped by the profitability gate
#   cycles            — number of prediction cycles run so far
#   started_at        — ISO timestamp of the run's start (UTC)
#   last_cycle_at     — ISO timestamp of the most recent cycle (UTC)
#   rewind_hours      — hours the clock is rewound (from .env), exposed so
#                        the UI can compute simulated NYC time
#   nav_history       — list of {ts, nav} snapshots recorded each cycle,
#                        used by the UI to draw the portfolio value chart
state = {
    "cash":           INITIAL_CASH,
    "nav":            INITIAL_CASH,
    "initial_cash":   INITIAL_CASH,
    "holdings":       {},
    "trades":         [],
    "trades_skipped": 0,
    "cycles":         0,
    "rewind_hours":   REWIND_HOURS,
    "time_speed":     TIME_SPEED,
    "nav_history":    [],
    "started_at":     None,
    "last_cycle_at":  None,
}


# ---------------------------------------------------------------------------
# Fee & price helpers
# ---------------------------------------------------------------------------

def compute_fee(notional: float) -> float:
    """
    Return the transaction fee for a trade of the given dollar notional.

    Model: max($5, 1.5% * notional). Mirrors a broker with a percentage
    fee that never falls below a $5 minimum — common for retail brokers.

    @param notional  Trade value in USD (shares * price, always positive).
    @return          Fee in USD.
    """
    return max(FEE_MIN, FEE_PCT * notional)


def last_price_for(ticker: str) -> float | None:
    """
    Return the most recent close price for `ticker` from data/<ticker>.csv.

    Reads the entire file and returns the last row's current_price. Returns
    None if the file is missing, empty, or unreadable — callers must handle
    the None case since thinly-traded tickers may never produce data.

    @param ticker  Stock symbol.
    @return        Last close price as float, or None.
    """
    path = os.path.join(DATA_DIR, f"{ticker}.csv")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            return None
        return float(rows[-1]["current_price"])
    except Exception:
        return None


def ticker_row_count(ticker: str) -> int:
    """Return the number of data rows (excluding header) for `ticker`."""
    path = os.path.join(DATA_DIR, f"{ticker}.csv")
    if not os.path.exists(path):
        return 0
    with open(path, "r") as fh:
        return max(0, sum(1 for _ in fh) - 1)


def active_tickers() -> list[str]:
    """
    Return tickers that currently have at least 2 data rows.

    prediction.cpp needs ≥2 bars to compute a simple return, so tickers
    with only the header or one bar are dropped from the universe for
    that cycle. They may become active later once data.py fetches more.
    """
    return [t for t in TICKERS if ticker_row_count(t) >= 2]


# ---------------------------------------------------------------------------
# prediction.exe invocation
# ---------------------------------------------------------------------------

def run_prediction(tickers: list[str], nav: float, investable: float) -> bool:
    """
    Invoke prediction.exe and return True on success.

    CLI contract (from prediction.cpp:1213):
        prediction.exe <data_dir> <output_dir> <total_capital>
                       <investable_capital> <TICKER1> [TICKER2] ...

    We pass NAV for both total and investable — prediction.cpp enforces
    its own 5% cash floor internally, so there is no need to pre-shrink.

    @param tickers     Tickers to include in this cycle's optimization.
    @param nav         Current portfolio NAV in USD.
    @param investable  Dollars available for allocation (== NAV here).
    @return            True if the binary exited 0 and produced outputs.
    """
    os.makedirs(TRADES_DIR, exist_ok=True)
    cmd = [
        PREDICTION_EXE,
        DATA_DIR,
        TRADES_DIR,
        f"{nav:.2f}",
        f"{investable:.2f}",
    ] + tickers

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
    except FileNotFoundError:
        log.error("prediction binary not found at %s", PREDICTION_EXE)
        return False
    except subprocess.TimeoutExpired:
        log.error("prediction.exe timed out after 120s")
        return False

    if result.returncode != 0:
        log.warning(
            "prediction.exe exit=%d stderr=%s",
            result.returncode, (result.stderr or "")[:300]
        )
        return False
    return True


def parse_portfolio_csv() -> list[dict]:
    """
    Parse trades/portfolio.csv into a list of trade recommendations.

    The CASH_RESERVE summary row is filtered out — it's informational
    and has no shares. Each returned dict has keys: ticker, action
    (lowercase: "buy"/"sell"/"hold"), shares (int, always positive).
    """
    path = os.path.join(TRADES_DIR, "portfolio.csv")
    if not os.path.exists(path):
        return []

    out = []
    with open(path, "r") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("ticker") == "CASH_RESERVE":
                continue
            try:
                shares = int(row["amount_of_shares"])
            except (KeyError, ValueError):
                continue
            out.append({
                "ticker": row["ticker"],
                "action": row["action"].strip().lower(),
                "shares": shares,
            })
    return out


def write_holdings_csv() -> None:
    """
    Rewrite trades/holdings.csv to mirror our authoritative state.

    Because we skip some of prediction.exe's sell recommendations, its
    own holdings.csv (which it wrote at the end of the previous call)
    can drift from the positions we actually hold. Overwriting the file
    with our post-gate holdings keeps prediction.exe in lockstep with
    reality — on the next call its load_holdings() reads the truth.

    Schema matches prediction.cpp's save_holdings() at line 1130:
        ticker,shares,avg_price,last_updated
    """
    path = os.path.join(TRADES_DIR, "holdings.csv")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ticker", "shares", "avg_price", "last_updated"])
        # state_lock is held by the caller during a cycle — safe to iterate.
        for ticker, h in state["holdings"].items():
            writer.writerow([
                ticker,
                h["shares"],
                f"{h['avg_buy']:.2f}",
                now_str,
            ])


# ---------------------------------------------------------------------------
# Portfolio mark-to-market
# ---------------------------------------------------------------------------

def _mark_to_market_locked() -> float:
    """
    Refresh last_price / market_value / unrealized_pnl on every holding
    and return the total market value of all positions.

    Caller must hold state_lock. If a ticker's current price is missing
    we fall back to its avg_buy so the holding still appears in NAV.
    """
    mtm_total = 0.0
    for ticker, h in state["holdings"].items():
        lp = last_price_for(ticker) or h["avg_buy"]
        h["last_price"]      = lp
        h["market_value"]    = lp * h["shares"]
        h["unrealized_pnl"]  = (lp - h["avg_buy"]) * h["shares"]
        mtm_total += h["market_value"]
    return mtm_total


# ---------------------------------------------------------------------------
# Main simulation cycle
# ---------------------------------------------------------------------------

def execute_cycle() -> None:
    """
    Run one full backtest cycle.

    Steps:
      1. Mark holdings to market and compute NAV.
      2. Invoke prediction.exe with NAV + current active ticker universe.
      3. Parse portfolio.csv and execute trades, sells first (they free
         up cash that buys can then consume), applying the fee model and
         profitability gate.
      4. Append executed trades to state["trades"], bump counters.
      5. Rewrite holdings.csv and persist state.json.
    """
    tickers = active_tickers()
    if not tickers:
        log.warning("No tickers with ≥2 data rows — skipping cycle")
        return

    # ---- step 1: NAV -----------------------------------------------------
    with state_lock:
        nav = state["cash"] + _mark_to_market_locked()
        state["nav"] = nav

    # ---- step 2: run predictor (outside lock — subprocess is slow) ------
    if not run_prediction(tickers, nav, nav):
        return

    recommendations = parse_portfolio_csv()

    # Separate sells from buys so we process sells first. prediction.exe
    # already did the same ordering internally when computing available
    # cash, but we must replicate it because our gating can drop some
    # sells (leaving less cash for buys than prediction.exe assumed).
    sells = [r for r in recommendations if r["action"] == "sell"]
    buys  = [r for r in recommendations if r["action"] == "buy"]
    ordered = sells + buys

    executed = 0
    skipped_unprofitable = 0
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---- step 3: execute trades under lock ------------------------------
    with state_lock:
        for rec in ordered:
            ticker = rec["ticker"]
            action = rec["action"]
            shares = rec["shares"]

            # hold rows and zero-share rows: nothing to do.
            if action == "hold" or shares <= 0:
                continue

            price = last_price_for(ticker)
            if price is None or price <= 0:
                continue

            notional = price * shares
            fee = compute_fee(notional)

            if action == "buy":
                # Must have enough cash for both the shares AND the fee.
                total_cost = notional + fee
                if state["cash"] < total_cost:
                    continue

                state["cash"] -= total_cost
                existing = state["holdings"].get(ticker)
                if existing:
                    # Weighted-average cost basis update.
                    old_shares = existing["shares"]
                    new_shares = old_shares + shares
                    existing["avg_buy"] = (
                        old_shares * existing["avg_buy"] + shares * price
                    ) / new_shares
                    existing["shares"] = new_shares
                else:
                    state["holdings"][ticker] = {
                        "shares":         shares,
                        "avg_buy":        price,
                        "last_price":     price,
                        "market_value":   notional,
                        "unrealized_pnl": 0.0,
                    }

                executed += 1
                state["trades"].append({
                    "ts":            now_iso,
                    "ticker":        ticker,
                    "side":          "buy",
                    "shares":        shares,
                    "price":         round(price, 4),
                    "notional":      round(notional, 2),
                    "fee":           round(fee, 2),
                    "pnl_realized":  0.0,
                    "cash_after":    round(state["cash"], 2),
                })

            elif action == "sell":
                existing = state["holdings"].get(ticker)
                if not existing or existing["shares"] <= 0:
                    continue

                # Can't sell more than we hold even if prediction.exe asks.
                sell_shares = min(shares, existing["shares"])
                notional    = price * sell_shares
                fee         = compute_fee(notional)

                # Profitability gate: realised P&L must exceed the fee.
                pnl = (price - existing["avg_buy"]) * sell_shares
                if pnl - fee <= 0:
                    skipped_unprofitable += 1
                    log.info(
                        "SKIP sell %s %d @ %.2f (pnl $%.2f ≤ fee $%.2f)",
                        ticker, sell_shares, price, pnl, fee,
                    )
                    continue

                state["cash"] += notional - fee
                existing["shares"] -= sell_shares
                if existing["shares"] == 0:
                    del state["holdings"][ticker]

                executed += 1
                state["trades"].append({
                    "ts":            now_iso,
                    "ticker":        ticker,
                    "side":          "sell",
                    "shares":        sell_shares,
                    "price":         round(price, 4),
                    "notional":      round(notional, 2),
                    "fee":           round(fee, 2),
                    "pnl_realized":  round(pnl - fee, 2),
                    "cash_after":    round(state["cash"], 2),
                })

        state["trades_skipped"] += skipped_unprofitable
        state["cycles"]         += 1
        state["last_cycle_at"]   = now_iso

        # Post-trade NAV refresh so the UI shows accurate values between
        # cycles and the predictor sees an up-to-date number next time.
        state["nav"] = state["cash"] + _mark_to_market_locked()

        # Record the NAV snapshot for the portfolio-value chart in the UI.
        state["nav_history"].append({
            "ts":  now_iso,
            "nav": round(state["nav"], 2),
        })

        # holdings.csv must be rewritten inside the lock so the on-disk
        # view is always consistent with `state["holdings"]`.
        write_holdings_csv()

    save_state()

    log.info(
        "cycle %d  nav=$%,.2f  cash=$%,.2f  positions=%d  exec=%d  skip=%d",
        state["cycles"], state["nav"], state["cash"],
        len(state["holdings"]), executed, skipped_unprofitable,
    )


def save_state() -> None:
    """Serialize `state` to state.json. Best-effort — logs but never raises."""
    try:
        with state_lock:
            snap = json.dumps(state, default=str)
        with open(STATE_FILE, "w") as fh:
            fh.write(snap)
    except Exception as e:
        log.warning("save_state failed: %s", e)


# ---------------------------------------------------------------------------
# HTTP UI
# ---------------------------------------------------------------------------

class UIHandler(BaseHTTPRequestHandler):
    """
    Minimal HTTP handler. Two routes:

      GET /            — serves backtest_ui.html (the single-page UI).
      GET /api/state   — returns `state` as JSON for the UI's poll loop.

    Everything else returns 404. We silence the default access log so the
    2-second UI polling doesn't drown out the simulation log.
    """

    def log_message(self, format, *args):
        return  # suppress access log

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send_file(UI_HTML, "text/html; charset=utf-8")
        elif self.path == "/api/state":
            with state_lock:
                payload = json.dumps(state, default=str).encode("utf-8")
            self._send_bytes(payload, "application/json")
        else:
            self.send_error(404)

    def _send_file(self, path: str, ctype: str) -> None:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except FileNotFoundError:
            self.send_error(404)
            return
        self._send_bytes(data, ctype)

    def _send_bytes(self, data: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def start_http_server() -> HTTPServer:
    """Start the UI server on a daemon thread and return the server object."""
    server = HTTPServer((HTTP_HOST, HTTP_PORT), UIHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True, name="http")
    t.start()
    log.info("HTTP UI ready: http://localhost:%d/", HTTP_PORT)
    return server


# ---------------------------------------------------------------------------
# data.py subprocess management
# ---------------------------------------------------------------------------

def spawn_data_py() -> subprocess.Popen:
    """
    Launch data.py in the background and pipe its logs into ours.

    stdout and stderr are merged and streamed line-by-line by a daemon
    thread — the prefix `[data]` makes them easy to distinguish from the
    backtester's own messages.
    """
    log.info("Launching data.py subprocess (REWIND_HOURS=%.2f, TIME_SPEED=%.0fx)",
             REWIND_HOURS, TIME_SPEED)
    proc = subprocess.Popen(
        [sys.executable, "-u", DATA_PY],
        cwd=BACKTEST_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def _drain():
        # Reads until EOF (i.e. data.py exits). Daemon thread dies with us.
        assert proc.stdout is not None
        for raw in iter(proc.stdout.readline, b""):
            msg = raw.decode(errors="replace").rstrip()
            if msg:
                log.info("[data] %s", msg)

    threading.Thread(target=_drain, daemon=True, name="data-drain").start()
    return proc


def wait_for_data(timeout_s: int = 300) -> None:
    """
    Block until data.py has written ≥2 rows for at least one ticker.

    We only need ONE active ticker to start a cycle — tickers that never
    produce data (thinly-traded or unknown symbols) are simply excluded.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        ready = active_tickers()
        if ready:
            log.info("Data warm-up complete — active tickers: %s", ready)
            return
        time.sleep(2)
    log.warning("Timed out waiting for data — starting anyway")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Top-level: boot subprocess, UI, and the simulation loop."""
    if REWIND_HOURS <= 0:
        log.error(
            "REWIND_HOURS must be > 0 in backtesting/.env — backtester "
            "only supports rewind (historical) mode."
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Full reset: wipe all artefacts from the previous run so every
    # invocation starts with a clean slate — no stale holdings, prices,
    # or trade history carry over.
    # ------------------------------------------------------------------

    # 1. Remove state.json (persisted portfolio snapshot).
    if os.path.exists(STATE_FILE):
        try:
            os.remove(STATE_FILE)
            log.info("Deleted previous state.json")
        except OSError as e:
            log.warning("Could not delete state.json: %s", e)

    # 2. Wipe data/ CSVs so prediction.exe doesn't see stale prices.
    if os.path.isdir(DATA_DIR):
        for fname in os.listdir(DATA_DIR):
            fpath = os.path.join(DATA_DIR, fname)
            try:
                os.remove(fpath)
            except OSError:
                pass
        log.info("Cleared data/ directory")

    # 3. Wipe trades/ directory (holdings.csv, portfolio.csv, etc.).
    os.makedirs(TRADES_DIR, exist_ok=True)
    for fname in os.listdir(TRADES_DIR):
        try:
            os.remove(os.path.join(TRADES_DIR, fname))
        except OSError:
            pass
    log.info("Cleared trades/ directory")

    # 4. Re-initialise in-memory state to defaults so leftover module-
    #    level values (if any import cached them) are overwritten.
    state["cash"]           = INITIAL_CASH
    state["nav"]            = INITIAL_CASH
    state["initial_cash"]   = INITIAL_CASH
    state["holdings"]       = {}
    state["trades"]         = []
    state["trades_skipped"] = 0
    state["cycles"]         = 0
    state["nav_history"]    = []
    state["last_cycle_at"]  = None

    state["started_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_state()

    data_proc = spawn_data_py()
    start_http_server()

    try:
        wait_for_data()
        log.info("Simulation loop started — cycle interval %.1fs (%.0fx speed)",
                 CYCLE_SECONDS / TIME_SPEED, TIME_SPEED)

        # Track the simulated clock so we know when rewind catches up to
        # real time and we should transition to live-speed cycling.
        sim_clock = datetime.now(timezone.utc) - timedelta(hours=REWIND_HOURS)
        live_mode_reached = False

        while True:
            t0 = time.time()
            try:
                execute_cycle()
            except Exception:
                log.exception("cycle failed")

            # Advance our local sim clock by one cycle (1 simulated minute).
            if not live_mode_reached:
                sim_clock += timedelta(seconds=CYCLE_SECONDS)

                # Check if the simulated clock has caught up to real time.
                if sim_clock >= datetime.now(timezone.utc):
                    live_mode_reached = True
                    log.info(
                        "Simulated time has caught up to real time — "
                        "switching to live-speed cycling (60 s)"
                    )
                    # Update state so the UI clock switches to real-time
                    # display and the speed badge disappears.
                    with state_lock:
                        state["rewind_hours"] = 0
                        state["time_speed"]   = 1
                    save_state()

            # In rewind mode, divide by TIME_SPEED so cycles run faster
            # (e.g. 10x → ~6 s per cycle). Once we transition to live mode,
            # revert to the full CYCLE_SECONDS cadence.
            if live_mode_reached:
                sleep_for = max(1.0, CYCLE_SECONDS - (time.time() - t0))
            else:
                sleep_for = max(0.5, (CYCLE_SECONDS / TIME_SPEED) - (time.time() - t0))
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        log.info("Ctrl+C — shutting down")

    finally:
        # Clean up the data.py child so we don't leak processes.
        if data_proc.poll() is None:
            data_proc.terminate()
            try:
                data_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                data_proc.kill()
        save_state()
        log.info("Final state saved to %s", STATE_FILE)


if __name__ == "__main__":
    main()
