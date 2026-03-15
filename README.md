# Canary AI

A hackathon project built for UNIHACK 2026.

## Tech Stack

| Layer    | Technology                  |
| -------- | --------------------------- |
| Frontend | React 19 + Vite 8           |
| Routing  | React Router DOM            |
| Backend  | FastAPI + Uvicorn (Python)  |
| Prediction | C++17 (g++)               |
| Database | Supabase (supabase-py)      |
| Data     | yfinance, Finnhub API       |
| Icons    | Lucide React                |
| Charts   | Recharts                    |
| Animation| GSAP                        |
| Async IO | aiofiles                    |
| Auth     | bcrypt (server-side hashing)|
| Chatbot  | Anthropic SDK (Claude)      |
| News AI  | Anthropic SDK (Claude opus-4-6) |

## Features

### Backend

- **Landing (React SPA)** — `GET /landing` serves the built React frontend; all sub-paths (`/landing/login`, `/landing/register`, `/landing/`) are handled by React Router via an SPA catch-all route; static assets (JS, CSS, images) are served from the same mount
- **Health-check endpoint** — `GET /` returns `{ "status": "ok" }`
- **Live stock tracking** — when tracking starts, 2 days of historical 1-minute candle data are backfilled into the CSV, then background tasks continue fetching the latest candle every 60 seconds
  - `POST /track/{ticker}` — start tracking a ticker (409 if already tracked)
  - `DELETE /track/{ticker}` — stop tracking a ticker (404 if not tracked)
  - `GET /track` — list all currently tracked tickers
- **Stock data endpoint** — `GET /stock-data/{ticker}` returns historical price data from the ticker's CSV file as a JSON array with fields: `timestamp`, `current_price`, `day_high`, `day_low`, `volume`, `market_cap`; returns 404 if the ticker has no data file
- **CSV persistence** — each tracked ticker gets its own CSV file in `backend/data/stock_training_data/` with columns: `timestamp, ticker, current_price, day_high, day_low, volume, market_cap`
- **General news tracking** — polls Finnhub for general market news every 60 seconds, deduplicates by article ID, and stores results in `backend/data/news/news.csv`
  - `POST /news` — start tracking news (409 if already tracking, 400 if API key missing)
  - `DELETE /news` — stop tracking news (404 if not tracking)
  - CSV columns: `id, category, datetime, headline, source, summary, url, image, related`
- **Time rewind mode** — set `TIME_REWIND_HOURS=N` in `.env` to shift the app's clock N hours into the past; yfinance fetches candles from the earlier window and Finnhub news is filtered to exclude articles published after the simulated time (set to `0` or leave unset for real-time behaviour)
- **Prediction module** (C++) — loads and parses per-ticker CSV data for stock price prediction
  - CLI interface: `./prediction.exe <data_dir> <output_dir> <total_capital> <investable_capital> <TICKER1> [TICKER2] ...` — accepts dynamic capital values and any number of tickers
  - Reads CSV files from the specified data directory (one file per ticker: `<ticker>.csv`)
  - Parses timestamps, prices, volume, and market cap into `StockRow` structs
  - Sorts data chronologically for time-series analysis
  - **Timestamp alignment** — aligns all stocks to a common timestamp index using forward-fill, handling gaps from low-liquidity trading
  - **Per-minute returns** — computes simple returns `r_t = (price_t - price_{t-1}) / price_{t-1}` for each aligned stock series; return vectors are same-length as input (index 0 = 0.0) to stay aligned with timestamps
  - **Covariance matrix** — computes mean returns and an NxN sample covariance matrix (with Bessel's correction) from the per-minute return vectors; exploits matrix symmetry and prints a labelled grid for verification
  - **Efficient frontier sampling** — generates ~1000 random long-only portfolios (weights ≥ 0, sum to 1) using uniform sampling + normalization, computes each portfolio's expected return (w^T * μ) and risk (√(w^T Σ w)), and identifies the min-variance and max-return portfolios
  - **Optimal portfolio selection** — finds the portfolio with the highest Sharpe ratio S = (r_p − r_f) / σ_p across all frontier portfolios (risk-free rate defaults to 0.0 for per-minute returns)
  - **Share allocation** — converts optimal weights into concrete whole-share counts using the investable capital (passed via CLI) and current stock prices; uses `floor()` rounding (no fractional shares) and reports per-stock invested amounts plus total rounding remainder returned to the cash reserve
  - **Trade plan computation** — compares target allocation against current holdings (read from `holdings.csv`), computes per-stock buy/sell/hold deltas, executes sells first to free cash, then processes buys with a 5% cash floor (derived from total capital CLI arg) to ensure minimum liquidity; partial buys are allowed when full buys would breach the floor
  - **Holdings persistence** — reads/writes `holdings.csv` in the output directory to track current portfolio positions across runs; first run starts with 0 shares, subsequent runs detect existing positions and only trade the difference
  - **Trade output CSV** — writes all trades (BUY, SELL, and HOLD) to `portfolio.csv` in the output directory with columns `ticker, action, amount_of_shares, total_change`; includes a `CASH_RESERVE` summary row showing the post-trade cash balance
  - Build: `cd backend/prediction && g++ -O2 -std=c++17 -o prediction prediction.cpp`
- **Prediction endpoints** — start/stop a background loop that re-runs the C++ prediction after all tracked stocks have fresh data
  - `POST /predict` — start the prediction loop (409 if already running, 400 if no stocks tracked)
  - `DELETE /predict` — stop the prediction loop (404 if not running)
  - Results are written to `backend/predictions/portfolio.csv`
  - The prediction loop automatically picks up newly added/removed tickers each cycle
  - **Supabase portfolio sync** — before each C++ run, the prediction loop fetches `cash_reserve` and `current_portfolio_value` from the DB to compute dynamic `total_capital` / `investable_capital`, and exports current holdings to `holdings.csv`; after a successful C++ run, `portfolio.csv` trade results are written back to Supabase (holdings upserted, transactions logged, cash reserve and portfolio value updated); falls back to $100M/$90M defaults if Supabase is unavailable
- **Supabase database CRUD** — full Create/Read/Update/Delete for 4 tables, addressed by `{username}`. All responses use `{"success": true, "data": ...}` / `{"success": false, "error": "..."}` envelope. Returns 503 when Supabase credentials are not configured.
  - **Users** (`/database/users`)
    - `GET /database/users` — list all users
    - `GET /database/users/{username}` — get a single user
    - `POST /database/users` — create a user (`{"username", "email", "password"}`); the plaintext password is hashed server-side with bcrypt before storage; automatically creates a zeroed-out portfolio row (`cash_reserve: 0`, `total_capital_invested: 0`, `current_portfolio_value: 0`) so every new user has a portfolio from the start
    - `POST /database/users/login` — verify credentials (`{"email", "password"}`); checks the plaintext password against the stored bcrypt hash and returns user data on success
    - `PUT /database/users/{username}` — update user fields (all optional: `username`, `email`, `password`, `api_key`, `trading_style`, `notifications`)
    - `DELETE /database/users/{username}` — delete a user
  - **Portfolios** (`/database/portfolios`)
    - `GET /database/portfolios` — list all portfolios
    - `GET /database/portfolios/{username}` — get portfolio for a user
    - `POST /database/portfolios` — create a portfolio (`{"username", "cash_reserve", "total_capital_invested", "current_portfolio_value"}`)
    - `POST /database/portfolios/{username}/deposit` — deposit cash into the portfolio (`{"amount"}`); increases cash_reserve and current_portfolio_value; amount must be positive
    - `POST /database/portfolios/{username}/withdraw` — withdraw cash from the portfolio (`{"amount"}`); decreases cash_reserve and current_portfolio_value; returns 400 if amount exceeds available cash reserve
    - `PUT /database/portfolios/{username}` — update portfolio fields
    - `DELETE /database/portfolios/{username}` — delete a user's portfolio
  - **Holdings** (`/database/holdings`)
    - `GET /database/holdings` — list all holdings
    - `GET /database/holdings/{username}` — get holdings for a user
    - `POST /database/holdings` — create a holding (`{"username", "ticker", "quantity", "average_buy_price"}`)
    - `PUT /database/holdings/{username}` — update holdings fields
    - `DELETE /database/holdings/{username}` — delete all holdings for a user
  - **Transactions** (`/database/transactions`)
    - `GET /database/transactions` — list all transactions
    - `GET /database/transactions/{username}` — get transactions for a user
    - `POST /database/transactions` — create a transaction (`{"username", "ticker", "tx_type", "quantity", "price_per_unit", "total_amount"}`)
    - `PUT /database/transactions/{username}` — update transaction fields
    - `DELETE /database/transactions/{username}` — delete all transactions for a user
- **Chat API** (`/chat`) — exposes the chatbot advisor as a REST API for the frontend ChatWindow; per-user session state is stored in memory, while preferences and memory are persisted to the Supabase `users` table (`memory` text column and `preferences` JSONB column)
  - `POST /chat` — send a message (`{"message", "username"}`) and receive `{"reply", "preferences_updated", "memory_entry", "state"}`; runs the full state machine (extraction, stock discussion/confirmation, field validation) per message; fetches the user's portfolio data (cash reserve, capital invested, portfolio value) from the `portfolios` table and injects it into the advisor's system prompt so the chatbot can reference the user's actual financial position when giving advice
  - **Automatic tracking integration** — when a user confirms a stock in the chatbot, tracking and all prediction loops (C++ efficient-frontier, Finnhub news, news-sentiment) are started automatically via `asyncio.create_task()`; when a stock is removed and no tracked tickers remain, the prediction and news-prediction loops are stopped automatically; uses lazy imports (`import main` inside helpers) to avoid circular dependencies; tracking failures are caught and logged without breaking the chat response
  - `POST /chat/reset` — clear the server-side session for a user (`{"username"}`); does not clear persisted DB memory/preferences
- **Per-user API keys** — each user stores their own Anthropic API key (plaintext) in the `users` table via `PUT /database/users/{username}`; the chatbot and news-prediction loop fetch the key from the DB at runtime instead of using a shared `.env` key; the `/chat` endpoint returns 403 if no key is configured
- **Preference Collection Chatbot** (`backend/chatbot/advisor.py`) — chatbot powered by the Anthropic SDK (Claude) that collects 4 investment preference data points through casual SMS-style conversation using a state machine architecture; available both as a standalone terminal app and via the `/chat` REST API
  - **State machine** with 4 states: `COLLECTING` (gathering base fields), `DISCUSSING_STOCK` (brief back-and-forth about a specific ticker), `CONFIRMING_STOCK` (yes/no commit decision), `ADVISING` (all fields set, open conversation)
  - Collects: `stocks_to_keep` (ticker list), `cash_reserve` (dollar amount), `trading_style` (risk-aggressive / balanced / risk-averse), `stock_preferences` (themes/sectors list)
  - Separate Claude API call extracts and validates fields from each user message; resolves company names to tickers (Apple → AAPL), normalizes cash amounts ($10k → 10000)
  - **Per-stock discussion flow** — each new ticker triggers a brief discussion before asking for a commit; multi-stock mentions (e.g. "keep AAPL, MSFT, TSLA") are queued and discussed one-by-one; when popping the next stock from the queue, the state transitions directly to `CONFIRMING_STOCK` (the discussion is already in the generated response) so the user's next "yes"/"no" is handled correctly
  - **Referential stock extraction** — when the user refers to stocks mentioned by the assistant (e.g. "invest into all of these", "add those"), the extraction model resolves the reference from conversation context and extracts the correct tickers
  - **Immediate save for non-stock fields** — cash_reserve, trading_style, and stock_preferences are saved to `preferences.json` instantly with no confirmation needed
  - **Stock confirmation** — stocks require explicit yes/no before adding; uses word-boundary matching (regex `\b`) so "none" won't false-trigger a "no" decline; ambiguous replies get one clarification attempt, then the stock is dropped
  - **Stock removal** — when the user asks to remove/drop/sell a stock (e.g. "remove AAPL"), the extraction model returns a `stocks_to_remove` field and the ticker is immediately removed from `stocks_to_keep` and persisted to `preferences.json`
  - **Declined stock tracking** — tickers that are declined or dropped during a session are remembered in a `declined_stocks` set and filtered out of future extraction results, preventing stale re-queuing from conversation context
  - Persistent memory via `memory.md` — logs every action (field saves, stock confirmations, stock declines, session-end context) with dated entries; loaded on startup so the advisor references prior context naturally
  - **Session-end memory** — on quit/exit/Ctrl+C, any pending stock discussions or queued tickers are logged to memory for continuity
  - Returning user support — loads `preferences.json` on startup to pre-populate fields; if all 4 fields are set, starts directly in ADVISING state
  - Edge cases: "none"/"no stocks" → empty list, "$0"/"zero" → 0.0, ambiguous trading style → asks to clarify, multiple fields in one message → all extracted
  - Commands: `quit`/`exit` exits, Ctrl+C exits cleanly
  - When used via the `/chat` REST API, the Anthropic API key is loaded per-user from the database; the standalone CLI still uses `ANTHROPIC_API_KEY` from `backend/.env`
  - Run: `cd backend/chatbot && python advisor.py`
- **News-sentiment trade overlay** (`backend/news_prediction/news_prediction.py`) — Python script that adjusts the C++ quant optimizer's trade plan based on Finnhub news sentiment via Claude (claude-opus-4-6)
  - Loads a Finnhub news CSV, the existing `portfolio.csv` (C++ output), and `holdings.csv`
  - Constructs a prompt instructing Claude to act as a portfolio risk manager reviewing the quant-optimized trades against recent news
  - Claude may hold, reduce, or reverse any position if news sentiment warrants it; enforces a 5 % cash floor rule
  - Parses and validates Claude's JSON response (retries once on malformed JSON); writes adjusted trades to `news_portfolio.csv` and updates `holdings.csv`
  - CLI: `python news_prediction.py --news news.csv --portfolio portfolio.csv --holdings holdings.csv --output news_portfolio.csv --total-capital 100000 --tickers AAPL MSFT`
  - `--dry-run` flag prints the prompt without calling Claude
  - API key loaded from `backend/.env` via python-dotenv
- **News-sentiment prediction loop** — recurring background loop that calls Claude every 60s to adjust the C++ trade plan based on Finnhub news sentiment; skips the Claude call when `news.csv` hasn't changed since the last cycle to avoid redundant API usage
  - `POST /news/predict` — start the news prediction loop (409 if already running)
  - `DELETE /news/predict` — stop the news prediction loop (404 if not running)
  - Each cycle: fetches portfolio state from Supabase, loads news/portfolio/holdings CSVs, builds a prompt, calls Claude, validates the response, writes `trades/news_portfolio.csv`, and syncs results back to Supabase (holdings upserted, transactions logged, cash reserve updated)
  - Guards per cycle: news tracking must be active, at least one ticker tracked, `trades/portfolio.csv` must exist, user `"a"`'s API key must exist in the DB
  - **Relaxed cash floor** — Claude's response is accepted when CASH_RESERVE is between 4–5% of total capital (soft warning); hard rejection only below 4%
- All data directories under `data/` are wiped on server restart
- Runs on `http://127.0.0.1:8000` with hot-reload via Uvicorn

### Frontend

- **Landing page** — full-page vertically scrollable tree scene (`/`); top section shows "Canary AI" title and a nest composite image with 3 invisible egg hover zones that reveal cracked canary overlays on hover (Login, Sign Up, Credits) with labels above the top shell piece; middle section is a seamlessly repeating bark texture trunk; bottom section uses pure CSS grass (5-layer SVG bumps tiling horizontally for added depth) with individual grass blade SVGs poking above the section edge for a natural non-flat transition, over a radial-gradient green ground (lighter center, darker edges) with scattered inline SVG flowers (white & pink petals) and rocks for a cartoony nature-scene feel, plus Login/Register buttons; GSAP entrance animations on title, nest, and buttons
- **Authentication context** — `AuthProvider` wraps the app to supply `user`, `login()`, `logout()`, and `updateUser()` via React context; persists the logged-in user object to `localStorage` so sessions survive page reloads; the landing route is guarded with a `<Navigate>` redirect to `/login` when no user is authenticated
- **Login & Register pages** — separate routes (`/landing/login`, `/landing/register`) with glassmorphic form cards over the animated sky background; puffy 3D inputs and submit buttons; GSAP pop-in card animation; back button (top-left arrow) for navigation; footer links to toggle between login and register; registration creates a real user in Supabase via `POST /database/users` (password hashed server-side with bcrypt); login verifies credentials via `POST /database/users/login`, then stores the returned user data in `AuthContext`; loading states disable the submit button during requests; server errors are displayed inline
- **Credits page** — glassmorphic card at `/credits` listing the team grouped by role (Frontend, Backend, Artwork) plus a full tech stack table (React, FastAPI, C++17, Supabase, GSAP, Recharts, Anthropic SDK, etc.); back button returns to the landing page; GSAP pop-in animation; scrollable if viewport is short
- **Theme system** — three modes: `auto`, `night`, and `day`
  - Auto mode cycles based on AEST time (day between 10:00–16:00, night otherwise) and re-evaluates every 60 seconds
  - Managed by `useTheme` hook and `ThemeProvider` context
- **GlassCard component** — reusable glassmorphism card with backdrop blur, configurable padding, and custom styling
- **Design token system** (`tokens.css`) — CSS custom properties for colors, spacing (4px base scale), typography, shadows, and border radii
- **Light & dark color palettes** — light mode defaults; dark mode activates via `.night` class on `<body>`
- **Animated canary birds** — 6 bright-yellow canary birds fly right-to-left across the sky at different depths and speeds; wings use a rotation-based flap animation (±30° via GSAP `svgOrigin`) for visible flapping motion, each bird bobs vertically, and the SVG features orange beaks and white eye highlights
- **GSAP** animation library integrated
- **Lucide React** icon library
- **Path aliasing** — `@` maps to `./src` via Vite config
- **Multi-window support** — multiple section windows can be open simultaneously with cascaded positioning (+30px offset per window), bring-to-front on click (z-order stacking), and independent close via window X button or Dock toggle; all open windows are highlighted in the Dock
- **Lego-style window snapping** — drag a window near another's edge and a semi-transparent ghost rectangle preview appears at ~30px proximity showing exactly where the window will land; release while the preview is visible to snap with a GSAP animation (snap-on-release); snapped windows move as a group when dragged; resize a shared edge and the bonded window resizes in sync; double-click a seam to unmerge with a playful bounce animation; supports N-window chaining across all 4 edges
- **Cloud-shaped navigation dock** — large (~750×300px) cloud dock positioned just below center of the viewport, built with inline SVG ellipses (no drop shadow); contains the Canary logo with a GSAP bobbing animation, a "Canary AI" branding label, and 5 cartoony, puffy nav buttons (Chat, Trades, Portfolio, Settings, Help) styled as rounded squares with a 3D embossed effect (darker border, lighter fill, bottom shadow) and text labels; cloud fill uses `var(--color-cloud)` so it adapts to day/night mode automatically
- **Section color tokens** — 15 CSS custom properties (primary / dark / light) for each navigation section, used for button hover/active states
- **ChatWindow** — purple-themed AI chat interface wired to the backend `POST /chat` endpoint; shows a greeting on mount, sends messages with the logged-in username, displays a typing indicator while waiting for the response, and renders preference-update system messages (`[✓ field: value]`) inline; the plus-icon button sends the current message (disabled while loading); speech bubbles, circular avatars, auto-scroll to newest message, send-on-Enter; opens from the Dock "Chat" button and renders inside the draggable/resizable `Window` shell
- **Corner Launchers** — two expandable quick-access menus in the bottom-left and bottom-right corners of the viewport; each features a 48px puffy trigger button (`+` icon that rotates to `×` on expand), 5 section-colored toggle buttons matching the Dock's navigation, and a "Clear All" action to close every open window; menu items animate in with staggered GSAP scale+fade, open windows show an outline ring, and both launchers work independently
- **Draggable & resizable window system** — generic `Window` shell component in `features/window/` with `useDrag` and `useResize` hooks; supports 8-direction resize handles, viewport-clamped dragging via the header bar, GSAP pop-in animation, per-section color theming via CSS custom properties, and a `closeIcon` prop for per-window custom close button images
- **PortfolioWindow** — live portfolio dashboard that fetches real data from Supabase; displays a summary card (total value, cash reserve, capital invested), interactive Recharts line charts for each tracked ticker showing price history, and a holdings table listing current positions (ticker, quantity, avg buy price, estimated value); empty states shown when no stocks are tracked or no holdings exist
- **Trades window** — opened/closed by the Trades dock button; displays a portfolio metrics card (total value, cash reserve, capital invested), deposit/withdraw cash management with inline validation errors, and a scrollable transaction history table showing past trades color-coded by type (buy=green, sell=red, hold=gray); wraps the generic Window shell with trades color tokens and a custom close icon PNG
- **Help window** — opened/closed by the Help (?) dock button and corner launchers; displays an 8-section step-by-step user guide covering Getting Started, Desktop Navigation, Chat, Portfolio, Trades, Settings, Window Management, and Theme; purple-themed using `--color-help-*` tokens with pill-shaped step number badges; wraps the generic Window shell (`HelpWindow.jsx / .css`)
- **Modular feature folders** — scaffolded directories for `dock`, `portfolio`, `sky`, and `window` features

## Project Structure

```
unihack-hackathon-submission/
├── backend/
│   ├── crud/                    # CRUD operations for each Supabase table
│   │   ├── helpers.py           # Username-to-ID resolution helpers
│   │   ├── users.py             # Users table CRUD
│   │   ├── portfolios.py        # Portfolios table CRUD
│   │   ├── holdings.py          # Holdings table CRUD
│   │   └── transactions.py      # Transactions table CRUD
│   ├── routers/                 # FastAPI routers (one per table + chat)
│   │   ├── chat.py              # /chat and /chat/reset endpoints (chatbot API)
│   │   ├── users.py             # /database/users endpoints
│   │   ├── portfolios.py        # /database/portfolios endpoints
│   │   ├── holdings.py          # /database/holdings endpoints
│   │   └── transactions.py      # /database/transactions endpoints
│   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── response.py          # success_response / error_response helpers
│   │   ├── users.py             # UserCreate, UserUpdate
│   │   ├── portfolios.py        # PortfolioCreate, PortfolioUpdate
│   │   ├── holdings.py          # HoldingCreate, HoldingUpdate
│   │   └── transactions.py      # TransactionCreate, TransactionUpdate, TxType enum
│   ├── data/                    # Runtime data directory
│   │   ├── news/                # General news CSV (auto-created at runtime)
│   │   └── stock_training_data/ # Per-ticker CSV files (auto-created at runtime)
│   ├── prediction/              # C++ stock prediction module
│   │   ├── prediction.cpp       # CSV loader, parser, and prediction driver
│   │   └── test_data/           # Test CSV files (AAPL.csv, BOBS.csv, MSFT.csv)
│   ├── predictions/             # Prediction output directory (auto-created at runtime)
│   │   ├── holdings.csv         # Current portfolio positions (auto-generated)
│   │   └── portfolio.csv        # Trade decisions output (auto-generated)
│   ├── chatbot/                   # Preference collection chatbot
│   │   ├── advisor.py             # Terminal chatbot — collects 4 investment preferences via casual conversation
│   │   ├── preferences.json       # Saved preferences (auto-generated after user confirmation)
│   │   └── memory.md              # Persistent session memory log (auto-generated)
│   ├── news_prediction/           # News-sentiment trade overlay
│   │   ├── __init__.py            # Package init (makes module importable)
│   │   └── news_prediction.py     # CLI script + importable helpers — adjusts quant trades via Claude API
│   ├── .env.example             # Template for required environment variables
│   ├── .gitignore               # Ignores .env and runtime data directories
│   ├── dependencies.py          # Supabase client init + FastAPI Depends
│   ├── main.py                  # FastAPI app with stock tracking, news, prediction, and landing page serving
│   └── requirements.txt         # Python dependencies (includes aiofiles for async static serving)
├── frontend/
│   ├── public/                # Static assets (favicon, icons)
│   ├── src/
│   │   ├── assets/
│   │   │   ├── chat/          # Chat icon assets (chat_close.png, chat_plus.png)
│   │   │   └── trades/        # Trades section images (close.png, etc.)
│   │   ├── components/        # Reusable UI components (GlassCard, CornerLauncher, SnapPreview, SnapSeams)
│   │   ├── contexts/          # React contexts (AuthContext, SnapContext)
│   │   ├── data/              # Data files
│   │   ├── features/          # Feature modules
│   │   │   ├── dock/          # Cloud-shaped navigation dock (Dock.jsx, Dock.css)
│   │   │   ├── portfolio/     # Portfolio feature (scaffold)
│   │   │   ├── sky/           # Animated sky background, clouds, birds
│   │   │   └── window/        # Draggable/resizable window system
│   │   │       ├── Window.jsx / .css       # Generic window shell (drag, resize, pop-in)
│   │   │       ├── TradesWindow.jsx / .css  # Trades section content
│   │   │       ├── ChatWindow.jsx / .css    # AI chat interface
│   │   │       ├── PortfolioWindow.jsx / .css # Portfolio overview
│   │   │       ├── SettingsWindow.jsx / .css # Settings panel (wired to backend via PUT /database/users)
│   │   │       └── HelpWindow.jsx / .css   # 8-section user guide (purple-themed)
│   │   ├── hooks/             # Custom React hooks
│   │   │   ├── useTheme.jsx   # Theme management hook
│   │   │   ├── useDrag.jsx    # Draggable position hook
│   │   │   └── useResize.jsx  # Resizable dimensions hook
│   │   ├── pages/             # Route-level page components
│   │   │   ├── AuthPages.css  # Shared auth page styles (glassmorphic card, puffy inputs)
│   │   │   ├── LandingPage.jsx # Landing page — tree scene with nest, eggs, trunk, and grass
│   │   │   ├── LandingPage.css # Landing page styles (nest, egg buttons, trunk, grass base)
│   │   │   ├── LoginPage.jsx  # Login form page (/login)
│   │   │   └── RegisterPage.jsx # Register form page (/register)
│   │   ├── styles/            # Global styles (base.css, tokens.css)
│   │   ├── utils/             # Utility functions
│   │   ├── App.jsx            # Root application component (Routes)
│   │   └── main.jsx           # Entry point (BrowserRouter)
│   ├── dist/                  # Production build output (generated by `npm run build`)
│   ├── index.html             # HTML shell
│   ├── package.json
│   └── vite.config.js         # Vite config with @ alias and base: '/landing/'
├── planning/
│   └── sms-notifications.md   # Two-way SMS feature plan (Twilio)
├── .gitignore                 # Root gitignore (chatbot secrets & runtime data)
├── CLAUDE.md                  # Instructions for Claude AI instances
└── README.md                  # This file
```

## Getting Started

### Prerequisites

- **Node.js** (v18+) and npm
- **Python** (3.10+) and pip
- **g++** with C++17 support (for prediction module)

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # then edit .env and add your Finnhub API key
python main.py
```

The API server starts at `http://127.0.0.1:8000`.

### Serving the frontend from FastAPI

Build the React app first, then start the backend — it will serve the SPA at `/landing`:

```bash
cd frontend
npm install
npm run build          # generates frontend/dist/

cd ../backend
pip install -r requirements.txt   # installs aiofiles + other deps
python main.py
```

Open `http://127.0.0.1:8000/landing` to use the app. React Router routes (`/landing/login`, `/landing/register`, `/landing/`) all work from this single server.

### Frontend (dev server)

```bash
cd frontend
npm install
npm run dev
```

Vite dev server starts at `http://localhost:5173` (default). With `basename="/landing"`, navigate to `http://localhost:5173/landing/` during development.
