# Canary AI

A hackathon project built for UNIHACK 2026.

## Tech Stack

| Layer    | Technology                  |
| -------- | --------------------------- |
| Frontend | React 19 + Vite 8           |
| Backend  | FastAPI + Uvicorn (Python)   |
| Icons    | Lucide React                |
| Animation| GSAP                        |

## Features

### Backend

- **Health-check endpoint** — `GET /` returns `{ "status": "ok" }`
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
│   ├── main.py              # FastAPI app with health-check endpoint
│   └── requirements.txt     # Python dependencies (fastapi, uvicorn)
├── frontend/
│   ├── public/              # Static assets (favicon, icons)
│   ├── src/
│   │   ├── components/      # Reusable UI components (GlassCard)
│   │   ├── data/            # Data files
│   │   ├── features/        # Feature modules (dock, portfolio, sky, window)
│   │   ├── hooks/           # Custom React hooks (useTheme)
│   │   ├── styles/          # Global styles (base.css, tokens.css)
│   │   ├── utils/           # Utility functions
│   │   ├── App.jsx          # Root application component
│   │   └── main.jsx         # Entry point
│   ├── index.html           # HTML shell
│   ├── package.json
│   └── vite.config.js       # Vite config with @ alias
├── CLAUDE.md                # Instructions for Claude AI instances
└── README.md                # This file
```

## Getting Started

### Prerequisites

- **Node.js** (v18+) and npm
- **Python** (3.10+) and pip

### Backend

```bash
cd backend
pip install -r requirements.txt
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
