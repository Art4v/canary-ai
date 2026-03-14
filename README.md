# Canary AI

A hackathon project built for UNIHACK 2026.

## Tech Stack

| Layer    | Technology                  |
| -------- | --------------------------- |
| Frontend | React 19 + Vite 8           |
| Backend  | FastAPI + Uvicorn (Python)  |
| Prediction | C++17 (g++)               |
| Data     | yfinance, Finnhub API       |
| Icons    | Lucide React                |
| Animation| GSAP                        |

## Features

### Backend

- **Health-check endpoint** — `GET /` returns `{ "status": "ok" }`
- **Live stock tracking** — when tracking starts, 2 days of historical 1-minute candle data are backfilled into the CSV, then background tasks continue fetching the latest candle every 60 seconds
  - `POST /track/{ticker}` — start tracking a ticker (409 if already tracked)
  - `DELETE /track/{ticker}` — stop tracking a ticker (404 if not tracked)
  - `GET /track` — list all currently tracked tickers
- **CSV persistence** — each tracked ticker gets its own CSV file in `backend/data/stock_training_data/` with columns: `timestamp, ticker, current_price, day_high, day_low, volume, market_cap`
- **General news tracking** — polls Finnhub for general market news every 60 seconds, deduplicates by article ID, and stores results in `backend/data/news/news.csv`
  - `POST /news` — start tracking news (409 if already tracking, 400 if API key missing)
  - `DELETE /news` — stop tracking news (404 if not tracking)
  - CSV columns: `id, category, datetime, headline, source, summary, url, image, related`
- **Time rewind mode** — set `TIME_REWIND_HOURS=N` in `.env` to shift the app's clock N hours into the past; yfinance fetches candles from the earlier window and Finnhub news is filtered to exclude articles published after the simulated time (set to `0` or leave unset for real-time behaviour)
- **Prediction module** (C++) — loads and parses per-ticker CSV data for stock price prediction
  - CLI interface: `./prediction.exe <data_dir> <output_dir> <TICKER1> [TICKER2] ...` — accepts any number of tickers dynamically
  - Reads CSV files from the specified data directory (one file per ticker: `<ticker>.csv`)
  - Parses timestamps, prices, volume, and market cap into `StockRow` structs
  - Sorts data chronologically for time-series analysis
  - **Timestamp alignment** — aligns all stocks to a common timestamp index using forward-fill, handling gaps from low-liquidity trading
  - **Per-minute returns** — computes simple returns `r_t = (price_t - price_{t-1}) / price_{t-1}` for each aligned stock series; return vectors are same-length as input (index 0 = 0.0) to stay aligned with timestamps
  - **Covariance matrix** — computes mean returns and an NxN sample covariance matrix (with Bessel's correction) from the per-minute return vectors; exploits matrix symmetry and prints a labelled grid for verification
  - **Efficient frontier sampling** — generates ~1000 random long-only portfolios (weights ≥ 0, sum to 1) using uniform sampling + normalization, computes each portfolio's expected return (w^T * μ) and risk (√(w^T Σ w)), and identifies the min-variance and max-return portfolios
  - **Optimal portfolio selection** — finds the portfolio with the highest Sharpe ratio S = (r_p − r_f) / σ_p across all frontier portfolios (risk-free rate defaults to 0.0 for per-minute returns)
  - **Share allocation** — converts optimal weights into concrete whole-share counts using $90M investable capital and current stock prices; uses `floor()` rounding (no fractional shares) and reports per-stock invested amounts plus total rounding remainder returned to the cash reserve
  - **Trade plan computation** — compares target allocation against current holdings (read from `holdings.csv`), computes per-stock buy/sell/hold deltas, executes sells first to free cash, then processes buys with a 5% cash floor ($5M of $100M total capital) to ensure minimum liquidity; partial buys are allowed when full buys would breach the floor
  - **Holdings persistence** — reads/writes `holdings.csv` in the output directory to track current portfolio positions across runs; first run starts with 0 shares, subsequent runs detect existing positions and only trade the difference
  - **Trade output CSV** — writes all trades (BUY, SELL, and HOLD) to `portfolio.csv` in the output directory with columns `ticker, action, amount_of_shares, total_change`; includes a `CASH_RESERVE` summary row showing the post-trade cash balance
  - Build: `cd backend/prediction && g++ -std=c++17 -o prediction prediction.cpp`
- **Prediction endpoints** — start/stop a background loop that re-runs the C++ prediction after all tracked stocks have fresh data
  - `POST /predict` — start the prediction loop (409 if already running, 400 if no stocks tracked)
  - `DELETE /predict` — stop the prediction loop (404 if not running)
  - Results are written to `backend/predictions/portfolio.csv`
  - The prediction loop automatically picks up newly added/removed tickers each cycle
- All data directories under `data/` are wiped on server restart
- Runs on `http://127.0.0.1:8000` with hot-reload via Uvicorn

### Frontend

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
- **Cloud-shaped navigation dock** — large (~750×300px) cloud dock positioned just below center of the viewport, built with inline SVG ellipses (no drop shadow); contains the Canary logo with a GSAP bobbing animation, a "Canary AI" branding label, and 5 cartoony, puffy nav buttons (Chat, Trades, Portfolio, Settings, Help) styled as rounded squares with a 3D embossed effect (darker border, lighter fill, bottom shadow) and text labels; cloud fill uses `var(--color-cloud)` so it adapts to day/night mode automatically
- **Section color tokens** — 15 CSS custom properties (primary / dark / light) for each navigation section, used for button hover/active states
- **ChatWindow** — purple-themed AI chat interface with speech bubbles, circular avatars, auto-scroll to newest message, send-on-Enter, a `chat_plus.png` image button to reset the conversation, and a send button; opens from the Dock "Chat" button and renders inside the draggable/resizable `Window` shell
- **SettingsWindow** — lavender-themed settings panel with a 3-column grid layout (label | control | action); includes API Key (masked input), Email, Password, Trading Style (dropdown: Balanced / Risk-Averse / Risk-Aggressive), and Notifications (CSS-only toggle switch); each row has its own Save button (stub handlers); opens from the Dock "Settings" button inside the draggable/resizable `Window` shell
- **Modular feature folders** — scaffolded directories for `dock`, `portfolio`, `sky`, and `window` features

## Project Structure

```
unihack-hackathon-submission/
├── backend/
│   ├── data/                    # Runtime data directory
│   │   ├── news/                # General news CSV (auto-created at runtime)
│   │   └── stock_training_data/ # Per-ticker CSV files (auto-created at runtime)
│   ├── prediction/              # C++ stock prediction module
│   │   ├── prediction.cpp       # CSV loader, parser, and prediction driver
│   │   └── test_data/           # Test CSV files (AAPL.csv, BOBS.csv, MSFT.csv)
│   ├── predictions/             # Prediction output directory (auto-created at runtime)
│   │   ├── holdings.csv         # Current portfolio positions (auto-generated)
│   │   └── portfolio.csv        # Trade decisions output (auto-generated)
│   ├── .env.example             # Template for required environment variables
│   ├── .gitignore               # Ignores .env and runtime data directories
│   ├── main.py                  # FastAPI app with stock tracking, news, and prediction
│   └── requirements.txt         # Python dependencies
├── frontend/
│   ├── public/                # Static assets (favicon, icons)
│   ├── src/
│   │   ├── assets/
│   │   │   ├── chat/          # Chat icon assets (chat_close.png, chat_plus.png)
│   │   │   └── settings/      # Settings icon assets (settings.png, settings_close.png)
│   │   ├── components/        # Reusable UI components (GlassCard)
│   │   ├── data/              # Data files
│   │   ├── features/          # Feature modules
│   │   │   ├── dock/          # Cloud-shaped navigation dock (Dock.jsx, Dock.css)
│   │   │   ├── portfolio/     # Portfolio feature (scaffold)
│   │   │   ├── sky/           # Animated sky background, clouds, birds
│   │   │   └── window/        # Window shell, TradesWindow, ChatWindow, SettingsWindow
│   │   ├── hooks/             # Custom React hooks (useTheme)
│   │   ├── styles/            # Global styles (base.css, tokens.css)
│   │   ├── utils/             # Utility functions
│   │   ├── App.jsx            # Root application component
│   │   └── main.jsx           # Entry point
│   ├── index.html             # HTML shell
│   ├── package.json
│   └── vite.config.js         # Vite config with @ alias
├── planning/
│   └── sms-notifications.md   # Two-way SMS feature plan (Twilio)
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

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite dev server starts at `http://localhost:5173` (default).
