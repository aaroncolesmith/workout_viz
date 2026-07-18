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

Copy `.env.example` to `.env`. Required variables:

- `DB_ENCRYPTION_MASTER_KEY` — 64 hex chars; wraps per-device SQLCipher DEKs.
  **Losing this key makes all user data unrecoverable** — keep an offline backup.

Optional: `DATA_DIR` (defaults to `./data` at repo root — resolved by
`identity_db.default_data_dir()`, the single source of truth). The `STRAVA_*`
vars are dormant; Strava routes only register when `STRAVA_AUTH_ENABLED=true`.

## Architecture

**No-login, per-device model** — every install has its own SQLCipher-encrypted
DB at `DATA_DIR/users/<user_id>/workouts.db`, keyed by a per-device DEK that
is stored AES-GCM-wrapped (under the master key) in the central identity DB
`DATA_DIR/users.db`. There are no accounts, no OAuth, no JWTs: on first
launch the iOS app silently registers a device and gets back an opaque
permanent token; that token *is* the `user_id`. All `/api/*` routes require
`Authorization: Bearer <device token>` via `Depends(get_current_user)`, which
just checks the token exists in the `users` table.

**Backend** — FastAPI + SQLCipher, Python venv at `./venv/`.

- `backend/main.py` — app entry point; registers routers; startup thread initialises the identity DB only (per-device DBs are provisioned at registration).
- `backend/api/deps.py` — `get_current_user` dependency: looks the Bearer token up in the identity DB, returns `user_id`.
- `backend/api/auth.py` — `POST /api/auth/device` (mints a new device token, no auth required), `DELETE /api/auth/account` (COMP-1 purge), `GET /api/auth/account/export` (COMP-2 ZIP export). Strava routes are gated behind `STRAVA_AUTH_ENABLED`.
- `backend/api/activities.py` — all `/api/` data routes: activity CRUD/filter, stats/overview, trends, calendar, best-segments, similarity, PCA, training blocks, routes (`PUT /api/routes/{id}` renames), HK deletions. Every route resolves `get_data_service(user_id)` itself.
- `backend/api/import_routes.py` — Apple Health XML upload + native HealthKit JSON sync (`POST /api/import/healthkit` for workouts, `POST /api/import/healthkit/metrics` for daily biometrics).
- `backend/api/health.py` — daily health metrics: `GET /api/health/summary` (all-metric snapshot) and `GET /api/health/metrics/{metric}` (series + 7d/30d rolling means + comparison block).
- `backend/services/health_metrics_service.py` — daily biometrics (resting HR, HRV, sleep, VO₂max, …) in the per-user `health_metrics` table, one row per (metric, day); `KNOWN_METRICS` is the canonical slug allowlist. All comparisons use trailing rolling means, anchored at the latest day with data. `conn=`-injected like the other analytics services.
- `backend/services/identity_db.py` — `users`/wrapped-DEK tables; `register_device()` mints a token and provisions the per-device DB; `default_data_dir()` and `get_user_db_path()` define the on-disk layout.
- `backend/services/key_provider.py` — master-key custody seam; wrap/unwrap DEKs, derive the identity-DB key. All crypto (including `backend/scripts/rotate_master_key.py`) goes through here.
- `backend/services/data_service.py` — per-user `DataService` via `get_data_service(user_id)` (LRU registry, max 200 live instances). Creates/repairs its schema on construction. SQLCipher DB is the source of truth; pandas only for analytics. Per-topic `_TTLCache`s; flushed on every write.
- `backend/services/database.py` — `get_conn(db_path, key)` returns a per-(thread, path) SQLCipher connection (WAL mode); `init_db(db_path, key)` creates schema + runs migrations, idempotent.
- `backend/services/similarity_service.py` — weighted feature scoring (distance 35%, pace 30%, HR 15%, elevation 10%, duration 10%) with a GPS polyline route-match multiplier. Requires an explicit `data_service=` argument (as do pca/fitness/insight/race-predictor/route services with `conn=`) — there are no global-connection fallbacks.
- `backend/services/fitness_service.py` — TRIMP CTL/ATL/TSB; resting HR comes from user_settings, else the 30-day `health_metrics` mean, else 60 (RDY-1). `get_readiness_v2` blends the TSB score with same-morning HRV/RHR/sleep deviations from 30-day baselines (weights 50/20/15/15, stale->2-days metrics drop out and weights renormalise) and returns explainable per-factor scores (RDY-2).
- `backend/services/correlation_service.py` — Phase D: `get_efficiency_trend` (EF = m/min per bpm, 42-day rolling mean + plain-language verdict), grain-agnostic aerobic decoupling from splits, and `get_effect_findings` (COR-1: sleep/HRV/RHR/rest-days cohorts on effort-adjusted pace; gated on n≥8 per cohort, Welch |t|≥2, effect ≥3 s/mi; direction taken from the data). Served by `GET /api/stats/efficiency` and `GET /api/stats/correlations`.
- `backend/services/digest_service.py` — COR-4 weekly narrative (`GET /api/stats/digest`): volume vs prior week, the COR-2 efficiency verdict, best-EF moment ranked vs the year, body drift, and the top COR-1 finding — composed entirely from existing services so it can't disagree with the charts.
- `backend/services/comparison_service.py` — CMP-1 post-workout verdict: cohort cascade (route → similar → distance band), rank, pace/HR deltas, efficiency quadrant, verdict sentence; uses `fitness_service.get_relative_effort` (TRIMP percentile over the trailing 90 days *ending at the activity's date*). Served by `GET /api/activities/{id}/comparison`, rendered by `ComparisonCard` at the top of ActivityDetail.
- `backend/services/pca_service.py` — PCA + KMeans on all activities of a type; results cached in the DataService analytics cache.
- `backend/services/splits_service.py` — the single splitter (`compute_splits`, buckets at `BUCKET_MILES` = 0.05 mi, sub-second times) and `rolling_fastest_segments`, the one grain-agnostic fastest-window implementation used by both summaries/PRs and the fastest-segments endpoint. The splits table holds mixed grains (legacy 0.1-mi + new 0.05-mi rows) — consumers must derive grain from rows, never assume it.
- `backend/services/apple_health_service.py` — streaming XML import (per-user background state) and `hk_activity_id()`, the single definition of HealthKit activity IDs used by both insert and delete paths. The single record-scan pass also accumulates daily health metrics (BIO-4): per-source max for steps/energy (multi-device double-count), interval-merged sleep attributed to the wake-up day.
- `backend/services/sync_service.py` — dormant Strava sync; raises `NotImplementedError` until re-wired for multi-tenancy.
- `backend/models/schemas.py` — all Pydantic request/response schemas.

**iOS** — SwiftUI wrapper (`ios/WorkoutViz/`) around a WKWebView, plus native HealthKit sync, plus a WidgetKit extension (`ios/VolkenWidgets/` — readiness score + morning deltas in 4 families). The widget is a separate binary: it duplicates the backend URL / keychain service constants (can't import app sources), reads the device token via the shared keychain access group `$(AppIdentifierPrefix)Aaronlytics.WorkoutViz` (keychain items are saved AfterFirstUnlock so locked-phone refreshes work), and caches its last snapshot for offline fallback.
`AuthService` owns the device token (Keychain) and `authorizedRequest()` — every native API call goes through it; `registerDeviceIfNeeded()` mints one silently on first launch, no UI. `SyncEngine` uses `HKAnchoredObjectQuery`; the anchor only advances when every upload/deletion in the batch succeeded. `NotificationManager` posts the post-sync verdict notification (CMP-5): incremental syncs only (never backfills, only workouts <6h old), notification permission asked contextually on the first verdict, taps deep-link the WebView to `/activity/{id}`. It also owns the opt-in morning readiness report (RDY-3): triggered by the sleep-data HK observer (so last night's sleep is already synced), once per day, 4–11 AM only, toggle in AccountView. `MetricsSyncEngine` rides along on every workout sync: daily-bucket `HKStatisticsCollectionQuery` per metric plus interval-merged sleep sessions → `POST /api/import/healthkit/metrics`; no anchors, just a last-synced date with a 7-day re-fetch overlap (backend upserts). The WebView injects the token into `localStorage` (`volken_session_token`) and re-injects whenever it changes.

**Frontend** — React 19 + Vite, dependencies in `frontend/`.

- `frontend/vite.config.js` — proxies `/api/*` to `http://localhost:8001`. All API calls use the relative `/api` base; no hardcoded backend URL in frontend code.
- `frontend/src/utils/api.js` — single API client module; all fetch calls live here. Attaches the Bearer token from `localStorage` and notifies the native bridge on 401.
- `frontend/src/stores/appState.js` — React Context providing cached overview, activities, and trends data. Also manages `comparisonSelections` (up to 5 activity IDs for side-by-side comparison).
- `frontend/src/App.jsx` — router: `/` → Dashboard, `/body` → Body (daily health metrics), `/activity/:id` → ActivityDetail, `/similarity` → SimilarityExplorer, `/auth/callback` → AuthCallback.
- `frontend/src/utils/metrics.js` — shared health-metric presentation config (accent colors, direction-of-goodness, value formatting) used by `pages/Body.jsx` and `components/MetricTile.jsx`.
- `frontend/src/pages/` — page-level components.
- `frontend/src/components/` — chart and UI components (Recharts, D3, Leaflet for route maps).

**Testing**

Tests live in `backend/tests/`. The `seeded_backend` fixture in `conftest.py` injects
`DB_ENCRYPTION_MASTER_KEY`/`DATA_DIR`, clears the `key_provider` LRU cache,
reloads the service modules, registers one test device in a fresh identity DB, and
seeds 4 activities (3 runs, 1 ride) into that device's encrypted DB. Use it for any test that
touches the DB — copying the env/cache-clear steps matters, or you get order-dependent
failures from stale cached keys.

**Data flow**

iOS HealthKit → `SyncEngine` (anchored, incremental) → `POST /api/import/healthkit`
(Bearer device token → `user_id`) → per-device SQLCipher DB at `DATA_DIR/users/<uid>/workouts.db` →
`DataService(user_id)` (reads + analytics cache) → FastAPI routes → WKWebView / Vite proxy →
React frontend. The Apple Health XML upload (`POST /api/import/apple-health`) is the web-side
ingestion path. Strava → `SyncService` is dormant.
