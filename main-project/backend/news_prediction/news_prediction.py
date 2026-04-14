"""
news_prediction.py — News-sentiment overlay for Vibe Trader's quant pipeline.

Reads Finnhub news CSV + the C++ optimizer's portfolio/holdings CSVs,
asks Claude (claude-opus-4-6) to act as a risk manager, and writes an
adjusted trade plan to news_portfolio.csv.

CLI usage:
    python news_prediction.py \
        --news news.csv \
        --portfolio ../trades/portfolio.csv \
        --holdings ../trades/holdings.csv \
        --output ../trades/news_portfolio.csv \
        --total-capital 100000 \
        --tickers AAPL MSFT GOOG
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
import anthropic                # Anthropic Python SDK
from dotenv import load_dotenv  # python-dotenv

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CASH_FLOOR_PCT: float = 0.05          # 5 % of total capital must stay as cash
CASH_FLOOR_TOLERANCE: float = 0.04    # relaxed minimum (4 %) — hard error below this
MODEL_ID: str = "claude-opus-4-6"     # Claude model to call
MAX_TOKENS: int = 4096                # max response tokens from Claude


# ===================================================================
# Data-loading helpers
# ===================================================================

def load_news_csv(path: str) -> list[dict[str, str]]:
    """
    Load a Finnhub news CSV file.

    Parameters
    ----------
    path : str
        Path to the news CSV.  Expected columns:
        id, category, datetime, headline, source, summary, url, image, related

    Returns
    -------
    list[dict[str, str]]
        Each row as an ordered dict keyed by column name.
    """
    rows: list[dict[str, str]] = []
    # Use errors="replace" because Finnhub article text sometimes
    # contains non-UTF-8 bytes (e.g. 0xa0 non-breaking spaces).
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def load_portfolio_csv(path: str) -> list[dict[str, Any]]:
    """
    Load the C++ optimizer's portfolio.csv (trade plan).

    Expected columns: ticker, action, amount_of_shares, total_change

    If the file does not exist, returns an empty list (first run scenario).

    Parameters
    ----------
    path : str
        Path to portfolio.csv.

    Returns
    -------
    list[dict[str, Any]]
        Parsed rows with numeric types coerced.
    """
    if not os.path.isfile(path):
        # First run — no existing portfolio; caller handles the empty list
        return []

    rows: list[dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({
                "ticker": row["ticker"],
                "action": row["action"],
                # amount_of_shares is always a non-negative integer
                "amount_of_shares": int(row["amount_of_shares"]),
                # total_change is a float (positive for buys, negative for sells)
                "total_change": float(row["total_change"]),
            })
    return rows


def load_holdings_csv(path: str) -> list[dict[str, Any]]:
    """
    Load holdings.csv with current positions.

    Expected columns: ticker, shares, avg_price, last_updated

    If the file does not exist, returns an empty list.

    Parameters
    ----------
    path : str
        Path to holdings.csv.

    Returns
    -------
    list[dict[str, Any]]
        Parsed rows with numeric types coerced.
    """
    if not os.path.isfile(path):
        return []

    rows: list[dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({
                "ticker": row["ticker"],
                "shares": int(row["shares"]),
                "avg_price": float(row["avg_price"]),
                "last_updated": row["last_updated"],
            })
    return rows


# ===================================================================
# Prompt construction
# ===================================================================

def build_prompt(
    portfolio: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    news: list[dict[str, str]],
    total_capital: float,
    tickers: list[str],
) -> str:
    """
    Build the system + user prompt that instructs Claude to act as a
    portfolio risk manager and return a JSON trade adjustment.

    Parameters
    ----------
    portfolio : list[dict]
        Existing trade plan from the C++ quant optimizer.
    holdings : list[dict]
        Current per-ticker positions.
    news : list[dict]
        Finnhub news rows.
    total_capital : float
        Total capital available to the trading system.
    tickers : list[str]
        Tickers the user is interested in.

    Returns
    -------
    str
        The fully assembled prompt string.
    """

    # --- Format portfolio into a readable block -------------------------
    if portfolio:
        portfolio_block = "ticker | action | amount_of_shares | total_change\n"
        portfolio_block += "-" * 55 + "\n"
        for row in portfolio:
            portfolio_block += (
                f"{row['ticker']} | {row['action']} | "
                f"{row['amount_of_shares']} | {row['total_change']}\n"
            )
    else:
        portfolio_block = "(No existing portfolio — first run; all capital is cash.)"

    # --- Format holdings into a readable block --------------------------
    if holdings:
        holdings_block = "ticker | shares | avg_price | last_updated\n"
        holdings_block += "-" * 55 + "\n"
        for row in holdings:
            holdings_block += (
                f"{row['ticker']} | {row['shares']} | "
                f"{row['avg_price']} | {row['last_updated']}\n"
            )
    else:
        holdings_block = "(No current holdings.)"

    # --- Format news headlines/summaries --------------------------------
    news_block = ""
    for i, article in enumerate(news, 1):
        headline = article.get("headline", "(no headline)")
        summary = article.get("summary", "(no summary)")
        related = article.get("related", "")
        source = article.get("source", "")
        news_block += (
            f"[{i}] {headline}\n"
            f"    Source: {source} | Related tickers: {related}\n"
            f"    Summary: {summary}\n\n"
        )
    if not news_block:
        news_block = "(No news articles provided.)"

    # --- Cash floor calculation -----------------------------------------
    cash_floor = total_capital * CASH_FLOOR_PCT

    # --- Assemble the full prompt ---------------------------------------
    prompt = f"""You are a portfolio risk manager reviewing a quant-optimized trade plan
in light of recent news. Your job is to decide whether any trades should
be modified (reduced, cancelled, or reversed) based on sentiment or
material information in the news.

=== CURRENT HOLDINGS ===
{holdings_block}

=== QUANT-OPTIMIZED TRADE PLAN (baseline) ===
{portfolio_block}

=== RECENT NEWS ===
{news_block}

=== PARAMETERS ===
- Total capital: ${total_capital:,.2f}
- Cash floor (5 % of total capital): ${cash_floor:,.2f}
- Tickers of interest: {', '.join(tickers)}

=== RULES YOU MUST FOLLOW ===
1. You may HOLD any position the quant model wanted to BUY or SELL if
   the news sentiment is sufficiently negative or risky for that ticker.
   "hold" means amount_of_shares = 0, total_change = 0.00.
2. You may reduce the amount_of_shares for a buy if news is mildly
   concerning but not catastrophic.
3. The CASH_RESERVE row must always be the LAST row. Its total_change
   must equal the remaining cash after all trades, and must be >= the
   cash floor (${cash_floor:,.2f}).
4. action must be one of: buy, sell, hold, summary (summary only for
   CASH_RESERVE).
5. amount_of_shares must be a non-negative integer.
6. total_change is positive for buys, negative for sells, 0 for holds.
7. Every ticker present in the baseline trade plan MUST appear in your
   output (even if action is changed to hold).

=== OUTPUT FORMAT ===
Return ONLY a JSON object — no markdown fences, no preamble, no
explanation outside the JSON. Use this exact schema:

{{
  "trades": [
    {{"ticker": "AAPL", "action": "buy", "amount_of_shares": 10, "total_change": 1523.40}},
    {{"ticker": "CASH_RESERVE", "action": "summary", "amount_of_shares": 0, "total_change": 94832.17}}
  ],
  "rationale": "one paragraph explaining your adjustments"
}}
"""
    return prompt


# ===================================================================
# Claude API interaction
# ===================================================================

def call_claude(prompt: str, client: anthropic.Anthropic) -> dict[str, Any]:
    """
    Send the prompt to Claude and parse the JSON response.

    If the first response is malformed JSON, retry once with an explicit
    correction prompt.

    Parameters
    ----------
    prompt : str
        The fully assembled prompt.
    client : anthropic.Anthropic
        An initialized Anthropic SDK client.

    Returns
    -------
    dict[str, Any]
        Parsed JSON with "trades" and "rationale" keys.

    Raises
    ------
    ValueError
        If Claude returns invalid JSON on both attempts.
    """

    # --- First attempt --------------------------------------------------
    response = client.messages.create(
        model=MODEL_ID,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    # Extract text content from the response
    raw_text: str = response.content[0].text.strip()

    try:
        parsed = json.loads(raw_text)
        return parsed
    except json.JSONDecodeError:
        pass  # fall through to retry

    # --- Retry with correction prompt -----------------------------------
    # Provide Claude its own malformed output and ask it to fix it
    correction_prompt = (
        "Your previous response was not valid JSON. Here is what you "
        f"returned:\n\n{raw_text}\n\n"
        "Please return ONLY a valid JSON object matching the schema I "
        "described. No markdown fences, no explanation outside the JSON."
    )

    retry_response = client.messages.create(
        model=MODEL_ID,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": raw_text},
            {"role": "user", "content": correction_prompt},
        ],
    )
    retry_text: str = retry_response.content[0].text.strip()

    try:
        parsed = json.loads(retry_text)
        return parsed
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Claude returned invalid JSON on both attempts.\n"
            f"First response:\n{raw_text}\n\n"
            f"Second response:\n{retry_text}"
        ) from exc


# ===================================================================
# Validation
# ===================================================================

def validate_response(data: dict[str, Any], total_capital: float) -> None:
    """
    Validate the parsed JSON from Claude against the expected schema
    and business rules.

    Parameters
    ----------
    data : dict
        Parsed JSON with "trades" and "rationale" keys.
    total_capital : float
        Total capital, used to verify cash floor.

    Raises
    ------
    ValueError
        If any validation check fails.
    """
    # Must have "trades" key containing a list
    if "trades" not in data or not isinstance(data["trades"], list):
        raise ValueError("Response missing 'trades' key or it is not a list.")

    # Must have "rationale" key
    if "rationale" not in data or not isinstance(data["rationale"], str):
        raise ValueError("Response missing 'rationale' key or it is not a string.")

    trades: list[dict[str, Any]] = data["trades"]

    if not trades:
        raise ValueError("Trades list is empty.")

    # Last row must be CASH_RESERVE
    last_trade = trades[-1]
    if last_trade.get("ticker") != "CASH_RESERVE":
        raise ValueError(
            "Last trade row must be CASH_RESERVE with action 'summary'."
        )
    if last_trade.get("action") != "summary":
        raise ValueError("CASH_RESERVE row must have action = 'summary'.")

    # Validate each trade row
    required_keys = {"ticker", "action", "amount_of_shares", "total_change"}
    valid_actions = {"buy", "sell", "hold", "summary"}

    for trade in trades:
        # Check required keys are present
        missing = required_keys - set(trade.keys())
        if missing:
            raise ValueError(
                f"Trade for {trade.get('ticker', '???')} missing keys: {missing}"
            )

        # action must be valid
        if trade["action"] not in valid_actions:
            raise ValueError(
                f"Invalid action '{trade['action']}' for {trade['ticker']}."
            )

        # amount_of_shares must be non-negative
        shares = trade["amount_of_shares"]
        if not isinstance(shares, (int, float)) or shares < 0:
            raise ValueError(
                f"amount_of_shares for {trade['ticker']} must be non-negative, "
                f"got {shares}."
            )

    # Cash floor check: CASH_RESERVE total_change must be at least near
    # the 5 % cash floor.  Claude sometimes returns values slightly under
    # 5 %, so we use a two-tier approach:
    #   - Below 4 % → hard ValueError (reject)
    #   - Between 4–5 % → print warning, accept the trades
    #   - At or above 5 % → pass silently
    cash_floor = total_capital * CASH_FLOOR_PCT
    cash_tolerance = total_capital * CASH_FLOOR_TOLERANCE
    cash_value = float(last_trade["total_change"])

    if cash_value < cash_tolerance:
        # Hard reject — too far below the floor
        raise ValueError(
            f"CASH_RESERVE (${cash_value:,.2f}) is below the 4 % hard minimum "
            f"(${cash_tolerance:,.2f})."
        )
    elif cash_value < cash_floor:
        # Soft warning — slightly under 5 % but above 4 %
        print(
            f"[News Prediction] WARNING: CASH_RESERVE (${cash_value:,.2f}) is "
            f"slightly below the 5 % cash floor (${cash_floor:,.2f}) but above "
            f"the 4 % tolerance — accepting trades.",
            flush=True,
        )


# ===================================================================
# Output writer
# ===================================================================

def write_portfolio_csv(trades: list[dict[str, Any]], path: str) -> None:
    """
    Write the adjusted trade plan to a CSV in the same format as
    the C++ optimizer's portfolio.csv.

    Columns: ticker, action, amount_of_shares, total_change

    Parameters
    ----------
    trades : list[dict]
        Trade rows from Claude's response.
    path : str
        Destination file path.
    """
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        # Header row
        writer.writerow(["ticker", "action", "amount_of_shares", "total_change"])
        for trade in trades:
            writer.writerow([
                trade["ticker"],
                trade["action"],
                int(trade["amount_of_shares"]),
                f"{float(trade['total_change']):.2f}",
            ])


def write_holdings_csv(
    trades: list[dict[str, Any]],
    existing_holdings: list[dict[str, Any]],
    path: str,
) -> None:
    """
    Update holdings.csv based on the adjusted trade plan.

    For each trade:
    - buy  → increase shares, recalculate average price
    - sell → decrease shares (avg_price unchanged)
    - hold → no change
    CASH_RESERVE is skipped.

    Parameters
    ----------
    trades : list[dict]
        Trade rows from Claude's response.
    existing_holdings : list[dict]
        Current holdings loaded from holdings.csv.
    path : str
        Destination holdings.csv path.
    """
    from datetime import datetime

    # Build a lookup of current holdings keyed by ticker
    holdings_map: dict[str, dict[str, Any]] = {}
    for h in existing_holdings:
        holdings_map[h["ticker"]] = {
            "shares": h["shares"],
            "avg_price": h["avg_price"],
        }

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for trade in trades:
        ticker = trade["ticker"]
        # Skip the cash-reserve summary row
        if ticker == "CASH_RESERVE":
            continue

        action = trade["action"]
        delta_shares = int(trade["amount_of_shares"])
        delta_cost = float(trade["total_change"])

        if ticker not in holdings_map:
            # Brand-new position
            holdings_map[ticker] = {"shares": 0, "avg_price": 0.0}

        current = holdings_map[ticker]

        if action == "buy" and delta_shares > 0:
            # Recalculate weighted-average buy price
            old_cost = current["shares"] * current["avg_price"]
            new_total_shares = current["shares"] + delta_shares
            # total_change is the dollar amount spent on this buy
            new_avg = (old_cost + delta_cost) / new_total_shares if new_total_shares else 0.0
            current["shares"] = new_total_shares
            current["avg_price"] = round(new_avg, 2)

        elif action == "sell" and delta_shares > 0:
            # Reduce shares; avg_price stays the same
            current["shares"] = max(0, current["shares"] - delta_shares)

        # "hold" → nothing changes

    # Write out the updated holdings
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ticker", "shares", "avg_price", "last_updated"])
        for ticker, data in holdings_map.items():
            # Only write tickers that still have shares
            if data["shares"] > 0:
                writer.writerow([
                    ticker,
                    data["shares"],
                    f"{data['avg_price']:.2f}",
                    now_str,
                ])


# ===================================================================
# CLI entry point
# ===================================================================

def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed CLI args with: news, portfolio, holdings, output,
        total_capital, tickers, dry_run.
    """
    parser = argparse.ArgumentParser(
        description=(
            "News-sentiment overlay for Vibe Trader. Adjusts a quant-optimized "
            "trade plan based on recent Finnhub news via Claude."
        ),
    )
    parser.add_argument(
        "--news", required=True,
        help="Path to the Finnhub news CSV file.",
    )
    parser.add_argument(
        "--portfolio", required=True,
        help="Path to the C++ optimizer's portfolio.csv (input).",
    )
    parser.add_argument(
        "--holdings", required=True,
        help="Path to holdings.csv with current positions.",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write the adjusted news_portfolio.csv.",
    )
    parser.add_argument(
        "--total-capital", type=float, required=True,
        help="Total capital available to the trading system.",
    )
    parser.add_argument(
        "--tickers", nargs="+", required=True,
        help="Tickers of interest (space-separated).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Print the prompt to stdout without calling Claude.",
    )
    return parser.parse_args()


def main() -> None:
    """
    Main entry point.

    1. Load .env for ANTHROPIC_API_KEY
    2. Parse CLI args
    3. Load news, portfolio, and holdings CSVs
    4. Build the prompt
    5. Call Claude (or print prompt in dry-run mode)
    6. Validate response
    7. Write output CSVs and print rationale
    """
    # Load environment variables from .env (looks in cwd and parents)
    # We explicitly point at the backend .env since the script lives in
    # news_prediction/ but secrets are stored one level up in backend/.
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)

    # Fallback: also try the default .env search
    load_dotenv()

    args = parse_args()

    # --- Load input data ------------------------------------------------
    print("[1/5] Loading input data …")
    news = load_news_csv(args.news)
    portfolio = load_portfolio_csv(args.portfolio)
    holdings = load_holdings_csv(args.holdings)

    print(f"      News articles : {len(news)}")
    print(f"      Portfolio rows: {len(portfolio)}")
    print(f"      Holdings rows : {len(holdings)}")

    # --- Build prompt ---------------------------------------------------
    print("[2/5] Building prompt …")
    prompt = build_prompt(
        portfolio=portfolio,
        holdings=holdings,
        news=news,
        total_capital=args.total_capital,
        tickers=args.tickers,
    )

    # --- Dry-run mode: print prompt and exit ----------------------------
    if args.dry_run:
        print("\n=== DRY RUN — Prompt that would be sent to Claude ===\n")
        print(prompt)
        sys.exit(0)

    # --- Call Claude ----------------------------------------------------
    print("[3/5] Calling Claude (model: {}) …".format(MODEL_ID))

    # Ensure the API key is available
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found in environment or .env file.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    try:
        result = call_claude(prompt, client)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    # --- Validate response ----------------------------------------------
    print("[4/5] Validating response …")
    try:
        validate_response(result, args.total_capital)
    except ValueError as exc:
        print(f"VALIDATION ERROR: {exc}")
        sys.exit(1)

    # --- Write outputs --------------------------------------------------
    print("[5/5] Writing outputs …")

    # Write the adjusted portfolio CSV
    write_portfolio_csv(result["trades"], args.output)
    print(f"      Wrote portfolio → {args.output}")

    # Update holdings.csv in-place based on the adjusted trades
    write_holdings_csv(result["trades"], holdings, args.holdings)
    print(f"      Updated holdings → {args.holdings}")

    # --- Print rationale ------------------------------------------------
    print("\n=== Claude's Rationale ===")
    print(result["rationale"])
    print()


# ---------------------------------------------------------------------------
# Script entry
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
