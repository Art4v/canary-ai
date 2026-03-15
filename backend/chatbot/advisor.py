"""
Preference Collection Chatbot — State Machine Edition
======================================================
A terminal-based chatbot that uses the Anthropic SDK to collect exactly 4
investment preference data points through natural, SMS-style conversation.
Uses a state machine to handle per-stock discussions and immediate saves
for non-stock fields.

States:
    COLLECTING       — gathering the 4 base fields (cash_reserve, trading_style,
                       stock_preferences, stocks_to_keep)
    DISCUSSING_STOCK — brief back-and-forth about a specific stock ticker
    CONFIRMING_STOCK — "Adding NVDA to your portfolio. Happy to commit?"
    ADVISING         — all 4 fields collected, open conversation / recommendations

Collected fields:
    1. stocks_to_keep    — list of uppercase ticker symbols to hold
    2. cash_reserve      — numeric dollar amount to keep as cash
    3. trading_style     — one of "risk-aggressive", "balanced", "risk-averse"
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
import re
import json
from datetime import datetime

# Third-party imports — anthropic for Claude API, dotenv for .env loading
from anthropic import Anthropic
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Directory containing this script (backend/chatbot/)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Path to the shared .env in the backend/ directory (one level up)
_ENV_PATH = os.path.join(_SCRIPT_DIR, "..", ".env")

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

# Module-level signal lists for yes/no detection
_POSITIVE_SIGNALS = [
    "yes", "yeah", "yep", "yup", "sure", "go for it",
    "confirm", "do it", "save", "add it", "looks good",
    "correct", "that's right", "perfect", "lgtm", "ok", "okay",
    "absolutely", "definitely", "for sure", "bet", "let's go",
]

_NEGATIVE_SIGNALS = [
    "no", "nah", "nope", "wait", "hold on", "change",
    "wrong", "not right", "fix", "update", "actually",
    "skip", "pass", "drop it", "never mind", "nvm",
]


class ConversationState:
    """
    Enum-like class representing the 4 states of the chatbot's state machine.

    COLLECTING       — gathering the 4 base preference fields
    DISCUSSING_STOCK — brief back-and-forth about a specific stock ticker
    CONFIRMING_STOCK — asking user to commit/decline a specific stock
    ADVISING         — all fields collected, open-ended investment conversation
    """
    COLLECTING = "COLLECTING"
    DISCUSSING_STOCK = "DISCUSSING_STOCK"
    CONFIRMING_STOCK = "CONFIRMING_STOCK"
    ADVISING = "ADVISING"


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

def build_advisor_system_prompt(
    collected: dict,
    memory_content: str,
    state: str,
    pending_stock: str | None = None,
) -> str:
    """
    Build a dynamic system prompt that tells Claude the current state,
    what has been collected, what still needs collecting, and any prior memory.

    Parameters
    ----------
    collected : dict
        Currently collected preference fields (may be partial).
    memory_content : str
        Raw contents of memory.md, or empty string if no prior memory.
    state : str
        Current ConversationState value (COLLECTING, DISCUSSING_STOCK, etc.).
    pending_stock : str or None
        The ticker symbol currently being discussed/confirmed (if any).

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

    # State-specific instructions — tells Claude exactly how to behave
    # depending on where we are in the conversation flow
    state_instructions = _build_state_instructions(state, pending_stock, missing)

    return f"""You are Canary AI, a casual investment preference collector. Your job is to \
collect exactly 4 pieces of information from the user through natural conversation, \
then help them with investment questions once everything's set.

## Your personality — SMS tone, enforced strictly
- Text like you're messaging a friend who knows finance
- Short sentences. Max 2-3 sentences per reply. No essays.
- Lowercase is fine, contractions encouraged, no corporate speak
- Examples of good tone: "nice, got it 👍", "solid pick — wanna lock it in?", \
"cool cool, what about cash?"
- Examples of BAD tone: "Thank you for providing that information. I have recorded your \
preference for technology stocks.", "Certainly! I'd be happy to help you with that."
- ONE question or topic per reply — never stack multiple questions

## The 4 fields you need to collect
1. stocks_to_keep — which stock tickers the user wants to hold onto (list, can be empty)
2. cash_reserve — how much cash to keep on the side (dollar amount, can be $0)
3. trading_style — one of: "risk-aggressive", "balanced", or "risk-averse"
4. stock_preferences — what kinds of stocks they're into (e.g. "tech", "dividends", "blue chip")

## Current collection status
{status_block}

## Fields still needed
{', '.join(missing) if missing else 'ALL COLLECTED ✓'}

## Current state: {state}
{state_instructions}

## General rules
- If the user says "none" or "no stocks" for stocks_to_keep → that's valid (empty list)
- If the user says "$0" or "zero" for cash → that's valid (0.0)
- If the user gives an ambiguous trading style answer (e.g. "medium" or "kinda risky"), \
ask them to clarify which of the 3 options fits best
- If the user provides multiple fields in one message, acknowledge all of them
- If the user wants to change a previously set field, accept the new value
- Non-stock fields (cash_reserve, trading_style, stock_preferences) are saved immediately — \
no confirmation needed for those. Just acknowledge with a brief "got it" style response.
- Stock tickers require a brief discussion before committing — don't auto-add them
{memory_section}"""


def _build_state_instructions(
    state: str,
    pending_stock: str | None,
    missing: list[str],
) -> str:
    """
    Generate state-specific behavioral instructions for the system prompt.

    Parameters
    ----------
    state : str
        Current ConversationState value.
    pending_stock : str or None
        Ticker being discussed/confirmed (if any).
    missing : list[str]
        List of field names still needed.

    Returns
    -------
    str
        Instruction block for the current state.
    """
    if state == ConversationState.COLLECTING:
        return (
            "You're gathering the 4 base fields. Ask about ONE missing field at a time.\n"
            "If the user mentions a stock ticker, briefly discuss why it's interesting \n"
            "before asking if they want to add it.\n"
            "When a non-stock field is provided, acknowledge it casually (it's auto-saved)."
        )

    elif state == ConversationState.DISCUSSING_STOCK:
        return (
            f"You're discussing the stock **{pending_stock}** with the user.\n"
            f"Give a brief, 1-sentence take on {pending_stock} — why it might be worth holding.\n"
            "Then ask if they want to add it to their portfolio.\n"
            "Keep it casual and short — this is a text conversation, not a research report."
        )

    elif state == ConversationState.CONFIRMING_STOCK:
        return (
            f"You just discussed **{pending_stock}**. Now you're waiting for a yes/no.\n"
            "If the user says yes → great, it'll be added (the system handles saving).\n"
            "If the user says no → that's fine, acknowledge and move on.\n"
            "If the answer is unclear, ask ONE more time to clarify, then drop it.\n"
            "Don't re-explain the stock — just ask for the commit decision."
        )

    elif state == ConversationState.ADVISING:
        return (
            "All 4 fields are collected! You're now in open advising mode.\n"
            "Help the user with investment questions, discuss stocks, or adjust preferences.\n"
            "If they mention new stocks, discuss them before adding.\n"
            "If they want to change a field, accept the update (system saves automatically).\n"
            "Stay casual and helpful — you're their finance-savvy friend."
        )

    # Fallback — shouldn't happen but be safe
    return ""


# ---------------------------------------------------------------------------
# Extraction prompt — JSON-only, no conversation, just structured output
# ---------------------------------------------------------------------------

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

- "stocks_to_remove": list of uppercase ticker symbols the user wants to REMOVE from their \
portfolio. Only set this when the user explicitly asks to remove, drop, or sell a stock \
(e.g. "remove AAPL", "drop nvidia", "take TSLA off my list"). Do NOT set this for normal \
stock mentions or additions.

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
    Adds a saved_at timestamp for tracking when this was last written.

    Parameters
    ----------
    collected : dict
        The current set of preference fields (may be partial or full).
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


def add_stock_to_preferences(collected: dict, ticker: str) -> None:
    """
    Idempotently add a single ticker to the stocks_to_keep list, then save.
    If the ticker is already present, this is a no-op (still saves to update timestamp).

    Parameters
    ----------
    collected : dict
        Current collected preferences (modified in place).
    ticker : str
        Uppercase ticker symbol to add (e.g. "AAPL").
    """
    # Ensure stocks_to_keep exists as a list
    if "stocks_to_keep" not in collected or collected["stocks_to_keep"] is None:
        collected["stocks_to_keep"] = []

    # Only add if not already present (idempotent)
    if ticker not in collected["stocks_to_keep"]:
        collected["stocks_to_keep"].append(ticker)

    # Persist immediately
    save_preferences(collected)


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
                        "Extract any NEW preference fields from the conversation, focusing on the USER's latest message. "
                        "If the user refers to stocks mentioned by the ASSISTANT (e.g. 'invest into all of these', "
                        "'add those', 'I want them all'), extract the tickers from the ASSISTANT's message that "
                        "the user is referring to. Return only JSON."
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

def validate_and_merge(extracted: dict, collected: dict) -> list[str]:
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
    list[str]
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


def _detect_new_tickers(extracted: dict, collected: dict, declined: set[str] | None = None) -> list[str]:
    """
    Find tickers in the extraction output that aren't already in the
    collected stocks_to_keep list and haven't been declined this session.

    Parameters
    ----------
    extracted : dict
        Raw extraction output (may contain "stocks_to_keep").
    collected : dict
        Current collected preferences.
    declined : set[str] or None
        Tickers declined or dropped during this session (won't be re-queued).

    Returns
    -------
    list[str]
        List of new ticker symbols not already saved or declined.
    """
    extracted_tickers = extracted.get("stocks_to_keep", [])
    if not isinstance(extracted_tickers, list):
        return []

    # Normalize to uppercase
    extracted_tickers = [t.upper() for t in extracted_tickers if isinstance(t, str)]

    # Get existing tickers (default to empty list)
    existing = collected.get("stocks_to_keep") or []

    # Build the declined set (default to empty if not provided)
    declined = declined or set()

    # Return only tickers not already present and not previously declined
    return [t for t in extracted_tickers if t not in existing and t not in declined]


def _check_yes_no(user_input: str) -> str:
    """
    Classify user input as 'yes', 'no', or 'ambiguous' based on signal lists.

    Parameters
    ----------
    user_input : str
        The raw user input string.

    Returns
    -------
    str
        One of 'yes', 'no', or 'ambiguous'.
    """
    lower = user_input.lower().strip()
    # Use word-boundary matching (\b) to avoid false positives —
    # e.g. "none" must NOT match the "no" signal, "okayed" must NOT match "ok"
    is_positive = any(re.search(r'\b' + re.escape(signal) + r'\b', lower) for signal in _POSITIVE_SIGNALS)
    is_negative = any(re.search(r'\b' + re.escape(signal) + r'\b', lower) for signal in _NEGATIVE_SIGNALS)

    if is_positive and not is_negative:
        return "yes"
    elif is_negative and not is_positive:
        return "no"
    else:
        return "ambiguous"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Run the interactive preference collection chatbot loop.

    Flow:
    1. Load API key from .env
    2. Load existing preferences.json (returning user) and memory.md
    3. State machine loop:
       - COLLECTING: gather fields, detect new stocks → DISCUSSING_STOCK
       - DISCUSSING_STOCK: Claude discusses ticker → CONFIRMING_STOCK
       - CONFIRMING_STOCK: yes/no/ambiguous → add or decline, pop queue
       - ADVISING: all fields set, open conversation
    4. Non-stock fields are saved immediately (no confirmation)
    5. Stock tickers are discussed one-by-one before committing
    6. Handle 'quit'/'exit' and Ctrl+C gracefully with session-end memory
    """
    # --- Load API key from the shared backend/.env ---
    load_dotenv(_ENV_PATH)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    # Validate that a real key is present
    if not api_key or api_key == "your_anthropic_api_key_here":
        print("ERROR: ANTHROPIC_API_KEY is not set or still has the placeholder value.")
        print(f"Please edit {os.path.abspath(_ENV_PATH)} and add your Anthropic API key.")
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

    # --- State machine variables ---
    # Current state — start in COLLECTING, or ADVISING if all fields already set
    state = ConversationState.ADVISING if all_fields_collected(collected) else ConversationState.COLLECTING
    # The stock ticker currently being discussed or confirmed
    pending_stock: str | None = None
    # Queue of tickers waiting to be discussed (for multi-stock mentions)
    stock_queue: list[str] = []
    # How many times we've asked for clarification on a stock confirm
    # (drop the stock after 2 ambiguous answers)
    clarification_count = 0
    # Tickers declined or dropped during this session — prevents re-queuing
    # when extraction picks them up again from conversation context
    declined_stocks: set[str] = set()
    # Track the state we should return to after finishing stock discussions
    # (either COLLECTING or ADVISING)
    return_state = state

    # --- Main conversation loop ---
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C or Ctrl+D — exit cleanly, log session end to memory
            print("\n\nsee ya! ✌️")
            # Log pending context if we were mid-discussion
            if pending_stock:
                append_memory(f"Session ended mid-discussion about {pending_stock} (not committed)")
            if stock_queue:
                append_memory(f"Session ended with queued stocks not discussed: {', '.join(stock_queue)}")
            break

        # Skip empty lines
        if not user_input:
            continue

        # Handle exit commands — same session-end memory logic
        if user_input.lower() in ("quit", "exit"):
            print("\nsee ya! ✌️")
            if pending_stock:
                append_memory(f"Session ended mid-discussion about {pending_stock} (not committed)")
            if stock_queue:
                append_memory(f"Session ended with queued stocks not discussed: {', '.join(stock_queue)}")
            break

        # Append the user message to conversation history
        messages.append({"role": "user", "content": user_input})

        # =================================================================
        # STATE: CONFIRMING_STOCK — check yes/no/ambiguous before calling Claude
        # =================================================================
        if state == ConversationState.CONFIRMING_STOCK:
            decision = _check_yes_no(user_input)

            if decision == "yes":
                # User confirmed — add the stock and save
                add_stock_to_preferences(collected, pending_stock)
                print(f"  [✓ {pending_stock} added to stocks_to_keep]")
                append_memory(f"User confirmed adding {pending_stock} to portfolio")
                # Reload memory so future prompts see the update
                memory_content = load_memory()

                # Pop next stock from queue or return to previous state
                if stock_queue:
                    pending_stock = stock_queue.pop(0)
                    # Set to CONFIRMING_STOCK — the response below already discusses
                    # the stock via the system prompt, so go straight to confirmation
                    state = ConversationState.CONFIRMING_STOCK
                    clarification_count = 0
                else:
                    pending_stock = None
                    clarification_count = 0
                    # Check if all fields are now collected
                    state = ConversationState.ADVISING if all_fields_collected(collected) else return_state

                # Generate a brief acknowledgment via Claude
                system_prompt = build_advisor_system_prompt(collected, memory_content, state, pending_stock)
                try:
                    response = client.messages.create(
                        model=_MODEL, max_tokens=256,
                        system=system_prompt, messages=messages,
                    )
                    reply = response.content[0].text
                    print(f"\nAdvisor: {reply}\n")
                    messages.append({"role": "assistant", "content": reply})
                except Exception as exc:
                    print(f"\n[API error: {exc}]\n")
                    messages.pop()
                continue

            elif decision == "no":
                # User declined — log to memory and move on
                append_memory(f"User declined adding {pending_stock} to portfolio")
                memory_content = load_memory()
                print(f"  [— {pending_stock} not added]")

                # Track this declined stock so it won't be re-queued
                declined_stocks.add(pending_stock)

                # Pop next stock from queue or return to previous state
                if stock_queue:
                    pending_stock = stock_queue.pop(0)
                    # Set to CONFIRMING_STOCK — the response below already discusses
                    # the stock via the system prompt, so go straight to confirmation
                    state = ConversationState.CONFIRMING_STOCK
                    clarification_count = 0
                else:
                    pending_stock = None
                    clarification_count = 0
                    state = ConversationState.ADVISING if all_fields_collected(collected) else return_state

                # Let Claude acknowledge the decline
                system_prompt = build_advisor_system_prompt(collected, memory_content, state, pending_stock)
                try:
                    response = client.messages.create(
                        model=_MODEL, max_tokens=256,
                        system=system_prompt, messages=messages,
                    )
                    reply = response.content[0].text
                    print(f"\nAdvisor: {reply}\n")
                    messages.append({"role": "assistant", "content": reply})
                except Exception as exc:
                    print(f"\n[API error: {exc}]\n")
                    messages.pop()
                continue

            else:
                # Ambiguous — clarify once, then drop on second ambiguity
                clarification_count += 1
                if clarification_count >= 2:
                    # Too many unclear answers — drop this stock
                    append_memory(f"Dropped {pending_stock} after ambiguous responses (not committed)")
                    memory_content = load_memory()
                    print(f"  [— {pending_stock} dropped (unclear response)]")

                    # Track this dropped stock so it won't be re-queued
                    declined_stocks.add(pending_stock)

                    if stock_queue:
                        pending_stock = stock_queue.pop(0)
                        # Set to CONFIRMING_STOCK — the response below already discusses
                        # the stock via the system prompt, so go straight to confirmation
                        state = ConversationState.CONFIRMING_STOCK
                        clarification_count = 0
                    else:
                        pending_stock = None
                        clarification_count = 0
                        state = ConversationState.ADVISING if all_fields_collected(collected) else return_state

                # Let Claude ask for clarification (or acknowledge the drop)
                system_prompt = build_advisor_system_prompt(collected, memory_content, state, pending_stock)
                try:
                    response = client.messages.create(
                        model=_MODEL, max_tokens=256,
                        system=system_prompt, messages=messages,
                    )
                    reply = response.content[0].text
                    print(f"\nAdvisor: {reply}\n")
                    messages.append({"role": "assistant", "content": reply})
                except Exception as exc:
                    print(f"\n[API error: {exc}]\n")
                    messages.pop()
                continue

        # =================================================================
        # STATE: DISCUSSING_STOCK — Claude's reply transitions to CONFIRMING
        # =================================================================
        if state == ConversationState.DISCUSSING_STOCK:
            # Generate Claude's discussion of the pending stock
            system_prompt = build_advisor_system_prompt(collected, memory_content, state, pending_stock)
            try:
                response = client.messages.create(
                    model=_MODEL, max_tokens=256,
                    system=system_prompt, messages=messages,
                )
                reply = response.content[0].text
                print(f"\nAdvisor: {reply}\n")
                messages.append({"role": "assistant", "content": reply})
            except Exception as exc:
                print(f"\n[API error: {exc}]\n")
                messages.pop()
                continue

            # After discussion, move to confirmation
            state = ConversationState.CONFIRMING_STOCK
            clarification_count = 0
            continue

        # =================================================================
        # STATE: COLLECTING or ADVISING — extract fields, handle stocks
        # =================================================================

        # Extract preference fields from the user's latest message
        extracted = extract_preferences(client, messages, collected)

        # Handle stock removals — if the user asked to remove tickers, do it immediately
        stocks_to_remove = extracted.get("stocks_to_remove", []) if extracted else []
        if isinstance(stocks_to_remove, list) and stocks_to_remove:
            current_stocks = collected.get("stocks_to_keep") or []
            for ticker in stocks_to_remove:
                ticker = ticker.upper() if isinstance(ticker, str) else str(ticker)
                if ticker in current_stocks:
                    current_stocks.remove(ticker)
                    print(f"  [✗ {ticker} removed from stocks_to_keep]")
                    append_memory(f"User removed {ticker} from portfolio")
            collected["stocks_to_keep"] = current_stocks
            save_preferences(collected)
            memory_content = load_memory()

        # Detect new tickers that need discussion before adding
        # Pass declined_stocks so previously declined tickers aren't re-queued
        new_tickers = _detect_new_tickers(extracted, collected, declined_stocks) if extracted else []

        # Remove stocks_to_keep and stocks_to_remove from extracted so validate_and_merge
        # doesn't process them — stocks go through the discussion/removal flow instead
        # auto-add them — stocks go through the discussion flow instead
        extracted_without_stocks = {k: v for k, v in extracted.items() if k not in ("stocks_to_keep", "stocks_to_remove")}

        # Validate and merge non-stock fields
        if extracted_without_stocks:
            updated = validate_and_merge(extracted_without_stocks, collected)
            if updated:
                # Save immediately for non-stock fields — no confirmation needed
                save_preferences(collected)
                for field in updated:
                    print(f"  [✓ {field}: {collected[field]}]")
                    # Log each field update to memory
                    if field == "cash_reserve":
                        append_memory(f"Cash reserve set to ${collected['cash_reserve']:,.2f}")
                    elif field == "trading_style":
                        append_memory(f"Trading style set to {collected['trading_style']}")
                    elif field == "stock_preferences":
                        prefs = collected["stock_preferences"]
                        if prefs:
                            append_memory(f"Stock preferences set to: {', '.join(prefs)}")
                # Reload memory after updates
                memory_content = load_memory()

        # Check if we should transition to ADVISING (all non-stock fields + stocks set)
        if state == ConversationState.COLLECTING and all_fields_collected(collected):
            state = ConversationState.ADVISING

        # If new tickers were mentioned, queue them for discussion
        if new_tickers:
            # Remember what state to return to after stock discussions
            return_state = ConversationState.ADVISING if all_fields_collected(collected) else ConversationState.COLLECTING
            # Set up the first ticker for discussion, queue the rest
            pending_stock = new_tickers[0]
            stock_queue.extend(new_tickers[1:])
            state = ConversationState.DISCUSSING_STOCK
            clarification_count = 0

            # Generate Claude's discussion of this stock
            system_prompt = build_advisor_system_prompt(collected, memory_content, state, pending_stock)
            try:
                response = client.messages.create(
                    model=_MODEL, max_tokens=256,
                    system=system_prompt, messages=messages,
                )
                reply = response.content[0].text
                print(f"\nAdvisor: {reply}\n")
                messages.append({"role": "assistant", "content": reply})
            except Exception as exc:
                print(f"\n[API error: {exc}]\n")
                messages.pop()
                continue

            # After discussion reply, move to confirmation
            state = ConversationState.CONFIRMING_STOCK
            continue

        # No new stocks — just generate a normal conversational response
        system_prompt = build_advisor_system_prompt(collected, memory_content, state, pending_stock)
        try:
            response = client.messages.create(
                model=_MODEL, max_tokens=256,
                system=system_prompt, messages=messages,
            )
            reply = response.content[0].text
            print(f"\nAdvisor: {reply}\n")
            messages.append({"role": "assistant", "content": reply})
        except Exception as exc:
            print(f"\n[API error: {exc}]\n")
            messages.pop()
            continue


# Only run when executed directly (not imported)
if __name__ == "__main__":
    main()
