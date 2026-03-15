"""
Preference Collection Chatbot
==============================
A terminal-based chatbot that uses the Anthropic SDK to collect exactly 4
investment preference data points through natural, casual (SMS-style)
conversation. Supports persistent memory across sessions and requires
explicit user confirmation before saving anything.

Collected fields:
    1. stocks_to_keep  — list of uppercase ticker symbols to hold
    2. cash_reserve    — numeric dollar amount to keep as cash
    3. trading_style   — one of "risk-aggressive", "balanced", "risk-averse"
    4. stock_preferences — list of stock-related preferences / themes

Usage:
    cd backend/chatbot
    python advisor.py

Commands:
    quit   — exit the chatbot
    exit   — exit the chatbot
    Ctrl+C — exit cleanly
"""

import os
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

# Path to the preferences JSON written after user confirmation
_PREFERENCES_PATH = os.path.join(_SCRIPT_DIR, "preferences.json")

# Path to the persistent memory markdown file
_MEMORY_PATH = os.path.join(_SCRIPT_DIR, "memory.md")

# Model used for both the conversation and the extraction call
_MODEL = "claude-sonnet-4-20250514"

# The 4 fields we need to collect before saving
_REQUIRED_FIELDS = ["stocks_to_keep", "cash_reserve", "trading_style", "stock_preferences"]

# Valid trading style values — extraction must match one of these exactly
_VALID_TRADING_STYLES = ["risk-aggressive", "balanced", "risk-averse"]


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

def build_advisor_system_prompt(collected: dict, memory_content: str) -> str:
    """
    Build a dynamic system prompt that tells Claude what has been collected
    so far, what still needs collecting, and any prior memory context.

    Parameters
    ----------
    collected : dict
        Currently collected preference fields (may be partial).
    memory_content : str
        Raw contents of memory.md, or empty string if no prior memory.

    Returns
    -------
    str
        The full system prompt string for the advisor persona.
    """
    # Build a status block showing what's done and what's still needed
    status_lines = []
    for field in _REQUIRED_FIELDS:
        if field in collected and collected[field] is not None:
            status_lines.append(f"  - {field}: COLLECTED → {collected[field]}")
        else:
            status_lines.append(f"  - {field}: STILL NEEDED")
    status_block = "\n".join(status_lines)

    # Figure out which fields are still missing
    missing = [f for f in _REQUIRED_FIELDS if f not in collected or collected[f] is None]

    # Build the memory context section (only if we have prior memory)
    memory_section = ""
    if memory_content.strip():
        memory_section = (
            "\n\n## Prior memory (from previous sessions)\n"
            "You can reference these past decisions naturally in conversation. "
            "For example, if the user previously declined a stock, you might ask "
            "\"last time you passed on NVDA — still a no?\"\n\n"
            f"{memory_content}"
        )

    return f"""You are Canary AI, a casual investment preference collector. Your job is to \
collect exactly 4 pieces of information from the user through natural conversation.

## Your personality
- Casual SMS tone — short sentences, no fluff, no corporate speak
- Friendly but direct — like texting a friend who happens to know finance
- Ask ONE question at a time — don't overwhelm
- Use lowercase freely, contractions are fine
- Keep responses short — 1-3 sentences max

## The 4 fields you need to collect
1. stocks_to_keep — which stock tickers the user wants to hold onto (list, can be empty)
2. cash_reserve — how much cash to keep on the side (dollar amount, can be $0)
3. trading_style — one of: "risk-aggressive", "balanced", or "risk-averse"
4. stock_preferences — what kinds of stocks they're into (e.g. "tech", "dividends", "blue chip")

## Current collection status
{status_block}

## Fields still needed
{', '.join(missing) if missing else 'ALL COLLECTED — proceed to confirmation'}

## Rules
- If the user says "none" or "no stocks" for stocks_to_keep → that's valid (empty list)
- If the user says "$0" or "zero" for cash → that's valid (0.0)
- If the user gives an ambiguous trading style answer (e.g. "medium" or "kinda risky"), \
ask them to clarify which of the 3 options fits best
- If the user provides multiple fields in one message, acknowledge all of them
- If the user wants to change a previously set field, accept the new value
- When all 4 fields are collected, show a plain-language summary of what you're about to save \
and ask for explicit confirmation before anything gets written
- NEVER auto-commit — always wait for a clear "yes" / "yeah" / "go for it" / "confirm" / "add it"
- If the user's confirmation is ambiguous, ask once more to clarify, then drop it if still unclear
- If the user declines confirmation, acknowledge it and ask what they want to change
{memory_section}"""


# Extraction prompt — JSON-only, no conversation, just structured output
_EXTRACTION_SYSTEM_PROMPT = """You are a JSON-only financial data extraction tool. \
You never produce any text outside of a JSON object.

Your job: extract investment preference fields from the user's latest message. \
Return ONLY a JSON object with any of these keys that you can extract:

- "stocks_to_keep": list of uppercase ticker symbols. Resolve company names to tickers \
(e.g. Apple → AAPL, Google → GOOGL, Microsoft → MSFT, Tesla → TSLA, Amazon → AMZN, \
Meta → META, Nvidia → NVDA). If the user says "none" or "no stocks", return [].

- "cash_reserve": numeric float value. Normalize amounts: "$10k" → 10000, "$5,000" → 5000, \
"50 grand" → 50000, "$0" or "zero" → 0.0. Must be >= 0.

- "trading_style": ONLY set this if the user's answer clearly maps to exactly one of: \
"risk-aggressive", "balanced", or "risk-averse". If ambiguous, do NOT include this field. \
Mappings: "aggressive"/"risky"/"yolo" → "risk-aggressive", \
"balanced"/"moderate"/"middle" → "balanced", \
"conservative"/"safe"/"careful"/"risk-averse" → "risk-averse".

- "stock_preferences": list of preference strings (e.g. ["tech", "dividends", "blue chip"]). \
Extract themes, sectors, or investment styles the user mentions.

If nothing is extractable from the message, return exactly: {}

IMPORTANT: Return ONLY valid JSON. No markdown, no explanation, no extra text."""


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def load_preferences() -> dict:
    """
    Load previously saved preferences from preferences.json.
    Returns the parsed dict, or an empty dict if the file doesn't exist
    or can't be parsed.
    """
    if not os.path.exists(_PREFERENCES_PATH):
        return {}
    try:
        with open(_PREFERENCES_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # Corrupted or unreadable file — start fresh
        return {}


def save_preferences(collected: dict) -> None:
    """
    Write the collected preferences to preferences.json.
    Only called after the user has explicitly confirmed.

    Parameters
    ----------
    collected : dict
        The full set of 4 validated preference fields.
    """
    # Add a timestamp so we know when this was last saved
    data = {**collected, "saved_at": datetime.now().isoformat()}
    with open(_PREFERENCES_PATH, "w") as f:
        json.dump(data, f, indent=2)


def load_memory() -> str:
    """
    Load the persistent memory file (memory.md).
    Returns the file contents as a string, or empty string if missing.
    """
    if not os.path.exists(_MEMORY_PATH):
        return ""
    try:
        with open(_MEMORY_PATH, "r") as f:
            return f.read()
    except IOError:
        return ""


def append_memory(entry: str) -> None:
    """
    Append a dated log entry to memory.md.
    Creates a new date header if today's date isn't already present.

    Parameters
    ----------
    entry : str
        The log line(s) to append (without date header — that's added automatically).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    date_header = f"## {today}"

    # Read existing content to check if today's header exists
    existing = load_memory()

    with open(_MEMORY_PATH, "a") as f:
        # Add the date header if it's not already in the file
        if date_header not in existing:
            # Add a blank line separator if the file already has content
            if existing.strip():
                f.write("\n\n")
            f.write(f"{date_header}\n")
        # Write the entry line(s)
        f.write(f"- {entry}\n")


# ---------------------------------------------------------------------------
# Extraction logic
# ---------------------------------------------------------------------------

def extract_preferences(client: Anthropic, messages: list[dict], collected: dict) -> dict:
    """
    Make a separate Claude API call to extract preference fields from the
    latest user message in the conversation.

    Parameters
    ----------
    client : Anthropic
        The initialized Anthropic API client.
    messages : list[dict]
        Full conversation history (used for context).
    collected : dict
        Currently collected fields (so extraction knows what's already set).

    Returns
    -------
    dict
        Extracted fields (may be empty if nothing was found).
    """
    try:
        # Build context from the last few messages (keep it focused)
        recent = messages[-4:] if len(messages) > 4 else messages
        conversation_text = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}" for msg in recent
        )

        # Tell the extraction model what's already collected so it focuses on new info
        collected_info = json.dumps(collected, indent=2) if collected else "{}"

        extraction_response = client.messages.create(
            model=_MODEL,
            max_tokens=256,
            system=_EXTRACTION_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Already collected fields:\n{collected_info}\n\n"
                        f"<conversation>\n{conversation_text}\n</conversation>\n\n"
                        "Extract any NEW preference fields from the USER's latest message. "
                        "Return only JSON."
                    ),
                }
            ],
        )

        # Parse the JSON response
        raw_text = extraction_response.content[0].text.strip()
        data = json.loads(raw_text)
        return data if isinstance(data, dict) else {}

    except (json.JSONDecodeError, Exception):
        # Extraction failures are non-fatal — just return empty
        return {}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_and_merge(extracted: dict, collected: dict) -> dict:
    """
    Validate extracted fields and merge valid ones into the collected dict.
    Invalid fields are silently dropped.

    Parameters
    ----------
    extracted : dict
        Raw extraction output from Claude.
    collected : dict
        Current state of collected preferences (modified in place).

    Returns
    -------
    dict
        List of field names that were newly set or updated.
    """
    updated = []

    # stocks_to_keep: must be a list of uppercase strings
    if "stocks_to_keep" in extracted:
        val = extracted["stocks_to_keep"]
        if isinstance(val, list):
            # Normalize: uppercase all tickers, filter out non-strings
            tickers = [t.upper() for t in val if isinstance(t, str)]
            collected["stocks_to_keep"] = tickers
            updated.append("stocks_to_keep")

    # cash_reserve: must be numeric and >= 0
    if "cash_reserve" in extracted:
        val = extracted["cash_reserve"]
        try:
            num = float(val)
            if num >= 0:
                collected["cash_reserve"] = num
                updated.append("cash_reserve")
        except (TypeError, ValueError):
            pass  # Skip invalid values

    # trading_style: must be one of the 3 valid values
    if "trading_style" in extracted:
        val = extracted["trading_style"]
        if isinstance(val, str) and val in _VALID_TRADING_STYLES:
            collected["trading_style"] = val
            updated.append("trading_style")

    # stock_preferences: must be a list of strings
    if "stock_preferences" in extracted:
        val = extracted["stock_preferences"]
        if isinstance(val, list):
            prefs = [p for p in val if isinstance(p, str)]
            collected["stock_preferences"] = prefs
            updated.append("stock_preferences")

    return updated


def all_fields_collected(collected: dict) -> bool:
    """
    Check whether all 4 required fields have been set.

    Parameters
    ----------
    collected : dict
        Current state of collected preferences.

    Returns
    -------
    bool
        True if every required field is present and not None.
    """
    return all(
        field in collected and collected[field] is not None
        for field in _REQUIRED_FIELDS
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Run the interactive preference collection chatbot loop.

    Flow:
    1. Load API key from .env
    2. Load existing preferences.json (returning user) and memory.md
    3. Loop: read input → respond casually → extract fields → confirm → save
    4. Handle 'quit'/'exit' and Ctrl+C gracefully
    """
    # --- Load API key from the .env next to this script ---
    load_dotenv(_ENV_PATH)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    # Validate that a real key is present
    if not api_key or api_key == "your_api_key_here":
        print("ERROR: ANTHROPIC_API_KEY is not set or still has the placeholder value.")
        print(f"Please edit {_ENV_PATH} and add your Anthropic API key.")
        print("Get a key at https://console.anthropic.com/")
        return

    # Initialise the Anthropic client
    client = Anthropic(api_key=api_key)

    # --- Load persisted state from disk ---
    # Load previously saved preferences (returning user gets pre-populated fields)
    collected = load_preferences()
    # Remove the saved_at timestamp — it's metadata, not a preference field
    collected.pop("saved_at", None)

    # Load prior session memory for context injection
    memory_content = load_memory()

    # Determine if this is a returning user (has at least one saved field)
    is_returning = bool(collected)

    # Print a welcome banner
    print("\n" + "=" * 60)
    print("  Canary AI — Investment Preferences")
    print("=" * 60)
    if is_returning:
        print("Welcome back! I've got your previous preferences loaded.")
        # Show what we already have
        for field in _REQUIRED_FIELDS:
            if field in collected:
                print(f"  {field}: {collected[field]}")
    else:
        print("Let's set up your investment preferences.")
        print("I'll ask you a few quick questions — won't take long.")
    print("Commands:  quit — exit")
    print("=" * 60 + "\n")

    # Conversation history in Anthropic SDK format
    messages: list[dict] = []

    # Track whether we're currently in the confirmation flow
    awaiting_confirmation = False

    # --- Main conversation loop ---
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C or Ctrl+D — exit cleanly
            print("\n\nsee ya! ✌️")
            break

        # Skip empty lines
        if not user_input:
            continue

        # Handle exit commands
        if user_input.lower() in ("quit", "exit"):
            print("\nsee ya! ✌️")
            break

        # Append the user message to conversation history
        messages.append({"role": "user", "content": user_input})

        # Build a dynamic system prompt reflecting current collection state + memory
        system_prompt = build_advisor_system_prompt(collected, memory_content)

        # --- Call Claude for a casual conversational response ---
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=256,
                system=system_prompt,
                messages=messages,
            )

            reply = response.content[0].text
            print(f"\nAdvisor: {reply}\n")

            # Store the assistant reply in conversation history
            messages.append({"role": "assistant", "content": reply})

        except Exception as exc:
            # API errors shouldn't kill the loop
            print(f"\n[API error: {exc}]\n")
            messages.pop()  # Remove the failed user message
            continue

        # --- If awaiting confirmation, check the user's response ---
        if awaiting_confirmation:
            # Check for positive confirmation signals in the user's message
            positive_signals = [
                "yes", "yeah", "yep", "yup", "sure", "go for it",
                "confirm", "do it", "save", "add it", "looks good",
                "correct", "that's right", "perfect", "lgtm", "ok", "okay"
            ]
            lower_input = user_input.lower().strip()

            # Check for negative signals
            negative_signals = [
                "no", "nah", "nope", "wait", "hold on", "change",
                "wrong", "not right", "fix", "update", "actually"
            ]

            is_positive = any(signal in lower_input for signal in positive_signals)
            is_negative = any(signal in lower_input for signal in negative_signals)

            if is_positive and not is_negative:
                # User confirmed — save preferences and log to memory
                save_preferences(collected)
                print("  [✓ Preferences saved to preferences.json]")

                # Build memory entries for what was confirmed
                memory_entries = []
                if "trading_style" in collected:
                    memory_entries.append(f"User confirmed trading style: {collected['trading_style']}")
                if "stocks_to_keep" in collected:
                    tickers = collected["stocks_to_keep"]
                    if tickers:
                        memory_entries.append(f"Stocks to keep: {', '.join(tickers)}")
                    else:
                        memory_entries.append("User has no stocks to keep (empty list)")
                if "cash_reserve" in collected:
                    memory_entries.append(f"Cash reserve set to ${collected['cash_reserve']:,.2f}")
                if "stock_preferences" in collected:
                    prefs = collected["stock_preferences"]
                    if prefs:
                        memory_entries.append(f"Stock preferences: {', '.join(prefs)}")

                # Append all entries to memory.md
                for entry in memory_entries:
                    append_memory(entry)
                print("  [✓ Session logged to memory.md]\n")

                awaiting_confirmation = False
                continue
            elif is_negative:
                # User declined — reset confirmation state, keep collecting
                awaiting_confirmation = False
                # Don't extract from this message — it's a rejection, not new data
                continue
            else:
                # Ambiguous — the advisor's reply already asked to clarify
                # Stay in confirmation mode for one more round
                continue

        # --- Extract preference fields from the user's latest message ---
        extracted = extract_preferences(client, messages, collected)

        if extracted:
            # Validate and merge into the collected dict
            updated = validate_and_merge(extracted, collected)
            if updated:
                # Show what was picked up
                for field in updated:
                    print(f"  [Got {field}: {collected[field]}]")
                print()

        # --- Check if all fields are now collected → enter confirmation flow ---
        if all_fields_collected(collected) and not awaiting_confirmation:
            awaiting_confirmation = True
            # The system prompt already instructs Claude to show a summary
            # and ask for confirmation, so the next advisor response will do that


# Only run when executed directly (not imported)
if __name__ == "__main__":
    main()
