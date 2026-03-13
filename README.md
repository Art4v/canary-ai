# Canary AI

A hackathon project built for UNIHACK 2026.

## Tech Stack

| Layer    | Technology                  |
| -------- | --------------------------- |
| Frontend | React 19 + Vite 8           |
| Backend  | FastAPI + Uvicorn (Python)  |
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
- **CSV persistence** — each tracked ticker gets its own CSV file in `backend/data/stock_training_data/` with columns: `timestamp, open, high, low, close, volume`
- **General news tracking** — polls Finnhub for general market news every 60 seconds, deduplicates by article ID, and stores results in `backend/data/news/news.csv`
  - `POST /news` — start tracking news (409 if already tracking, 400 if API key missing)
  - `DELETE /news` — stop tracking news (404 if not tracking)
  - CSV columns: `id, category, datetime, headline, source, summary, url, image, related`
- **Time rewind mode** — set `TIME_REWIND_HOURS=N` in `.env` to shift the app's clock N hours into the past; yfinance fetches candles from the earlier window and Finnhub news is filtered to exclude articles published after the simulated time (set to `0` or leave unset for real-time behaviour)
- All data directories under `data/` are wiped on server restart
- Runs on `http://127.0.0.1:8000` with hot-reload via Uvicorn

### Frontend

- **Theme system** — three modes: `auto`, `night`, and `day`
  - Auto mode cycles based on AEST time (day between 10:00–16:00, night otherwise) and re-evaluates every 60 seconds
  - Managed by `useTheme` hook and `ThemeProvider` context
- **GlassCard component** — reusable glassmorphism card with backdrop blur, configurable padding, and custom styling
- **Design token system** (`tokens.css`) — CSS custom properties for colors, spacing (4px base scale), typography, shadows, and border radii
- **Light & dark color palettes** — light mode defaults; dark mode activates via `.night` class on `<body>`
- **GSAP** animation library integrated
- **Lucide React** icon library
- **Path aliasing** — `@` maps to `./src` via Vite config
- **Modular feature folders** — scaffolded directories for `dock`, `portfolio`, `sky`, and `window` features

## Project Structure

```
unihack-hackathon-submission/
├── backend/
│   ├── data/                    # Runtime data directory
│   │   ├── news/                # General news CSV (auto-created at runtime)
│   │   └── stock_training_data/ # Per-ticker CSV files (auto-created at runtime)
│   ├── .env.example             # Template for required environment variables
│   ├── .gitignore               # Ignores .env and runtime data directories
│   ├── main.py                  # FastAPI app with stock tracking and news tracking
│   └── requirements.txt         # Python dependencies
├── frontend/
│   ├── public/                # Static assets (favicon, icons)
│   ├── src/
│   │   ├── components/        # Reusable UI components (GlassCard)
│   │   ├── data/              # Data files
│   │   ├── features/          # Feature modules (dock, portfolio, sky, window)
│   │   ├── hooks/             # Custom React hooks (useTheme)
│   │   ├── styles/            # Global styles (base.css, tokens.css)
│   │   ├── utils/             # Utility functions
│   │   ├── App.jsx            # Root application component
│   │   └── main.jsx           # Entry point
│   ├── index.html             # HTML shell
│   ├── package.json
│   └── vite.config.js         # Vite config with @ alias
├── CLAUDE.md                  # Instructions for Claude AI instances
└── README.md                  # This file
```

## Getting Started

### Prerequisites

- **Node.js** (v18+) and npm
- **Python** (3.10+) and pip

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
