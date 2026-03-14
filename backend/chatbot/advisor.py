"""
Investment Advisor Chatbot
==========================
A terminal-based chatbot that uses the Anthropic SDK to chat with users
about investment preferences. After each exchange, a separate Claude API
call extracts mentioned stock tickers and writes them to watchlist.csv.

Usage:
    cd backend/chatbot
    python advisor.py

Commands:
    reset  — clear conversation history and watchlist
    quit   — exit the chatbot
    exit   — exit the chatbot
    Ctrl+C — exit cleanly
"""

import os
import csv
import json
from datetime import datetime

# Third-party imports — anthropic for Claude API, dotenv for .env loading
from anthropic import Anthropic
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Path to the .env file sitting next to this script
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_SCRIPT_DIR, ".env")

# Path to the watchlist CSV written after every exchange
_WATCHLIST_PATH = os.path.join(_SCRIPT_DIR, "watchlist.csv")

# Model used for both the conversation and the ticker-extraction call
_MODEL = "claude-sonnet-4-20250514"

# System prompt that shapes the advisor's personality
_ADVISOR_SYSTEM_PROMPT = (
    "You are an expert stock market investment advisor. "
    "Give concise, actionable advice. Ask clarifying questions about the "
    "user's risk tolerance, time horizon, and investment goals when the "
    "conversation is vague. Mention specific ticker symbols when relevant. "
    "You are friendly but professional."
)

# System prompt for the ticker-extraction utility call
_EXTRACTION_SYSTEM_PROMPT = (
    "You are a JSON-only financial data extraction tool. "
    "You never produce any text outside of a JSON object. "
    "Your sole job is to extract stock ticker symbols mentioned or "
    "discussed in the provided conversation and return them in the "
    "exact format requested."
)


# ---------------------------------------------------------------------------
# Watchlist helpers
# ---------------------------------------------------------------------------

def reset_watchlist() -> None:
    """
    Overwrite watchlist.csv with just the header row.
    Called on startup and when the user types 'reset'.
    """
    with open(_WATCHLIST_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "added_at"])


def update_watchlist(messages: list[dict]) -> None:
    """
    Make a separate Claude API call to extract every stock ticker mentioned
    in the conversation so far, then overwrite watchlist.csv with the results.

    Parameters
    ----------
    messages : list[dict]
        The full conversation history in Anthropic SDK format
        (list of {"role": ..., "content": ...} dicts).

    This function is wrapped in a broad try/except so that extraction
    failures never crash the main chat loop.
    """
    try:
        # Build a plain-text representation of the conversation for extraction
        conversation_text = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}" for msg in messages
        )

        # Ask Claude to extract tickers as a JSON object
        extraction_response = client.messages.create(
            model=_MODEL,
            max_tokens=256,
            system=_EXTRACTION_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "<conversation>\n"
                        f"{conversation_text}\n"
                        "</conversation>\n\n"
                        "Extract all stock ticker symbols mentioned or discussed "
                        "in the conversation above. Return ONLY a JSON object in "
                        'this exact format: {"tickers": ["AAPL", "MSFT", ...]}. '
                        "If no tickers are mentioned, return {\"tickers\": []}."
                    ),
                }
            ],
        )

        # Parse the JSON response — Claude should return pure JSON
        raw_text = extraction_response.content[0].text.strip()
        data = json.loads(raw_text)
        tickers = data.get("tickers", [])

        # Write the tickers to CSV (overwrite every time)
        now = datetime.now().isoformat()
        with open(_WATCHLIST_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["ticker", "added_at"])
            for ticker in tickers:
                writer.writerow([ticker, now])

        # Print a one-liner summary so the user knows what was captured
        if tickers:
            print(f"  [Watchlist updated: {', '.join(tickers)}]")
        else:
            print("  [Watchlist: no tickers detected yet]")

    except Exception as exc:
        # Never crash the main loop — just warn and continue
        print(f"  [Watchlist update failed: {exc}]")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Run the interactive terminal chatbot loop.

    Flow:
    1. Load and validate the API key from .env
    2. Reset watchlist.csv to header-only
    3. Loop: read user input → call Claude → print reply → extract tickers
    4. Handle 'reset', 'quit'/'exit', and Ctrl+C gracefully
    """
    global client  # used by update_watchlist helper

    # --- Load API key from the .env next to this script ---
    load_dotenv(_ENV_PATH)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    # Validate that a real key is present
    if not api_key or api_key == "your_api_key_here":
        print("ERROR: ANTHROPIC_API_KEY is not set or still has the placeholder value.")
        print(f"Please edit {_ENV_PATH} and add your Anthropic API key.")
        print("Get a key at https://console.anthropic.com/")
        return

    # Initialise the Anthropic client with the loaded key
    client = Anthropic(api_key=api_key)

    # Reset watchlist on startup so we start fresh
    reset_watchlist()

    # Print a welcome banner
    print("\n" + "=" * 60)
    print("  Canary AI — Investment Advisor Chatbot")
    print("=" * 60)
    print("Ask me about stocks, portfolios, or investment strategies.")
    print("Commands:  reset — restart conversation  |  quit — exit")
    print("=" * 60 + "\n")

    # Conversation history in Anthropic SDK format
    messages: list[dict] = []

    # --- Main conversation loop ---
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C or Ctrl+D — exit cleanly with no stack trace
            print("\n\nGoodbye! Happy investing.")
            break

        # Skip empty lines
        if not user_input:
            continue

        # Handle special commands
        if user_input.lower() == "reset":
            messages.clear()
            reset_watchlist()
            print("\nConversation and watchlist cleared. Let's start fresh!\n")
            continue

        if user_input.lower() in ("quit", "exit"):
            print("\nGoodbye! Happy investing.")
            break

        # Append the user message to history
        messages.append({"role": "user", "content": user_input})

        # Call the Claude API with the full conversation history
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=1024,
                system=_ADVISOR_SYSTEM_PROMPT,
                messages=messages,
            )

            # Extract the text reply from the response
            reply = response.content[0].text

            # Print the advisor's reply
            print(f"\nAdvisor: {reply}\n")

            # Append the assistant reply so context builds up
            messages.append({"role": "assistant", "content": reply})

            # Run the ticker-extraction side-call and update watchlist.csv
            update_watchlist(messages)
            print()  # blank line for readability

        except Exception as exc:
            # API errors shouldn't kill the loop — let the user retry
            print(f"\n[API error: {exc}]\n")
            # Remove the failed user message so history stays consistent
            messages.pop()


# Only run when executed directly (not imported)
if __name__ == "__main__":
    main()
