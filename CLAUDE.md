# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
./start.sh          # starts both backend (port 8001) and frontend (port 5173)
```

Or run individually:
```bash
# Backend
./venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd frontend && npm run dev
```

API docs available at `http://localhost:8001/docs`.

## Commands

```bash
# Backend tests
pytest                                          # all tests
pytest backend/tests/test_services.py -k name  # single test

# Frontend
cd frontend && npm run lint
cd frontend && npm run build
```

## Environment

Copy `.env.example` to `.env`. Required variables: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REDIRECT_URI` (defaults to `http://localhost:5173/auth/callback`). Optional: `DATA_DIR`, `DB_PATH`.

Strava OAuth tokens are persisted to `data/.strava_token.json`.

## Architecture

**Backend** — FastAPI + SQLite, Python venv at `./venv/`.

- `backend/main.py` — app entry point; registers routers, startup hook that initialises DB and warms the `DataService` singleton.
- `backend/api/activities.py` — all `/api/` routes: activity CRUD/filter, sync trigger, similarity, PCA, stats/overview, trends, calendar, best-segments.
- `backend/api/auth.py` — Strava OAuth2 flow (`/auth/url`, `/auth/callback`, `/auth/status`).
- `backend/services/data_service.py` — `DataService` singleton (via `get_data_service()`). SQLite is the source of truth; pandas is only used for analytics (overview stats, trends, rolling averages). Has a `_TTLCache` (5 min TTL) wrapping the two expensive paths: PCA vectors and similarity scores. Cache is flushed on every `add_activities()` / `update_activities()` call.
- `backend/services/database.py` — thread-local SQLite connections with WAL mode. Call `init_db(path)` once at startup; use `get_conn()` everywhere else.
- `backend/services/similarity_service.py` — weighted feature scoring (distance 35%, pace 30%, HR 15%, elevation 10%, duration 10%) with a GPS polyline route-match multiplier.
- `backend/services/pca_service.py` — PCA + KMeans on all activities of a type; results cached in the DataService analytics cache.
- `backend/services/sync_service.py` — background Strava sync via a thread; poll `/api/activities/sync/status` for progress.
- `backend/models/schemas.py` — all Pydantic request/response schemas.

**Frontend** — React 19 + Vite, dependencies in `frontend/`.

- `frontend/vite.config.js` — proxies `/api/*` to `http://localhost:8001`. All API calls use the relative `/api` base; no hardcoded backend URL in frontend code.
- `frontend/src/utils/api.js` — single API client module; all fetch calls live here.
- `frontend/src/stores/appState.js` — React Context providing cached overview, activities, and trends data. Also manages `comparisonSelections` (up to 5 activity IDs for side-by-side comparison).
- `frontend/src/App.jsx` — router: `/` → Dashboard, `/activity/:id` → ActivityDetail, `/similarity` → SimilarityExplorer, `/auth/callback` → AuthCallback.
- `frontend/src/pages/` — 4 page-level components.
- `frontend/src/components/` — chart and UI components (Recharts, D3, Leaflet for route maps).

**Testing**

Tests live in `backend/tests/`. The `seeded_backend` fixture in `conftest.py` monkeypatches `DATA_DIR`/`DB_PATH`, reloads all service modules into a fresh temp database, and seeds 4 activities (3 runs, 1 ride). Use it for any test that touches the DB.

**Data flow**

Strava → `SyncService` (background thread) → SQLite (`workouts.db`) → `DataService` (reads + analytics cache) → FastAPI routes → Vite proxy → React frontend. CSV files in `data/` are written by SyncService for backward-compatibility only; `DataService` no longer reads them.
