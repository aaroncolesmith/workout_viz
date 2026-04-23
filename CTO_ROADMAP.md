# 🏃 Workout Viz — CTO Technical Roadmap

> **Last Updated:** March 22, 2026
> **Status:** Active — Sprint 4 / P1 API hardening
> **Author:** CTO / Principal Architect

---

## Executive Summary

Workout Viz is a personal fitness analytics platform that transforms raw Strava data into actionable training intelligence. After a thorough technical audit, the product is in a **strong MVP state** — the data pipeline, core visualizations, and similarity engine are functional. However, several architectural decisions from the rapid prototyping phase are now becoming bottlenecks that will compound as we scale features.

### Where We Are
- ✅ **Working MVP**: Dashboard, Activity Detail with comparison, PCA Explorer, Strava OAuth + Sync
- ✅ **Unique Value**: Similarity engine with route-aware matching, PCA clustering, progress tracking
- ✅ **Solid Design System**: Premium dark theme, glassmorphism, thoughtful data visualization

### Where We Need to Go
1. **Reliability First** — Fix fragile data loading, eliminate server-hang pathways, add error boundaries
2. **Interactivity** — Ship chart zoom (drag-to-zoom is partially implemented but broken), add brushing and linking across charts
3. **Architecture** — Move from in-memory CSV/pandas to a proper database, add caching, implement state management
4. **Intelligence** — Automate the insights that currently require manual exploration: PRs, streaks, performance trends, training load

### Strategic Themes

| Theme | What It Means | Why It Matters |
|-------|--------------|----------------|
| 🛡️ **Resilience** | The app should never crash or hang—even with degraded data | Users lose trust after one broken session |
| 🔍 **Deep Interaction** | Zoom, brush, filter, cross-link—every chart is explorable | Small differences between activities are the whole point |
| 🧠 **Proactive Intelligence** | The app tells YOU when something changed, not the other way around | Turns a dashboard into a coach |
| 📱 **Accessibility** | Works on mobile, works on a slow connection, works with a11y tools | Reach and inclusivity |

---

## Technical Audit — Key Findings

### 🔴 Critical Issues (Impacting Reliability & UX)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| C1 | **Entire dataset loaded into memory on startup** | `data_service.py` — `_load_data()` loads 3 CSVs into pandas DataFrames at init time. No caching, no lazy loading. With ~3.3MB activities + ~14MB splits, startup delay grows linearly. | Slow cold starts, high memory, crashes with large datasets |
| C2 | **Iterative lat/lng parsing is O(n) per row** | `data_service.py` L106-116 — row-by-row `for idx, val` loop with `ast.literal_eval` on every row for lat/lng and polyline | Startup time ~2-4s wasted on string parsing |
| C3 | ~~**No error boundaries in React**~~ | ✅ **Fixed** — `ErrorBoundary.jsx` created; all three page routes wrapped | |
| C4 | ~~**Chart zoom is partially implemented and broken**~~ | ✅ **Fixed** — `ReferenceArea` imported, `getFilteredData` rewritten with numeric range filtering, `activeLabel` used for reliable drag capture, zoom resets on axis toggle, crosshair cursor + hint added | |
| C5 | **Sync can hang the server** | `sync_service.py` — deep sync iterates the entire Strava API generator synchronously on the main thread. | Server becomes unresponsive during sync |
| C6 | ~~**CSV write contention**~~ | ✅ **Fixed** — `threading.Lock` added to `DataService`; all writes use `_safe_csv_write()` (temp-file + atomic rename) | |
| C7 | **`ActivityDetail.jsx` is 879 lines** — a God Component | Single file handles: header, stat cards, map, radar, progress timeline, pace chart, HR chart, fastest segments, similar activities, zoom state, comparison state, delta calculations | Unmaintainable; any change risks regressions |

### 🟡 Architectural Debt

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| A1 | **No state management** | Frontend — every page manages its own state via `useState`/`useEffect` | No shared state; navigation loses all context, duplicate API calls |
| A2 | **Module-level singletons** | All backend services use `_service: Optional[Service] = None` pattern | Not suitable for async (FastAPI is async-capable but singleton init is sync), untestable |
| A3 | **No API response validation** | Frontend `api.js` — raw `res.json()` with no schema validation, backend has Pydantic schemas but doesn't use them for responses | Frontend can crash on unexpected shapes |
| A4 | **No caching layer** | Backend — every request re-queries the in-memory DataFrames. PCA is recomputed on every request. | Wasted compute; PCA/similarity are expensive |
| A5 | **Mixed CSV column naming** | Splits CSV uses `activity_id` and `id` interchangeably (`data_service.py` L312) | Fragile, defensive coding throughout |
| A6 | **No tests** | Full stack — zero unit tests, zero integration tests, zero E2E tests | Every deploy is a gamble |
| A7 | **Hardcoded CORS origins** | `main.py` L20-24 — only localhost:5173 and localhost:3000 | Blocks any deployment beyond local dev |
| A8 | **No Docker / deployment story** | `start.sh` is bash-only, no Dockerfile, no CI/CD | Manual deploys, environment drift |

### 🟢 Strengths to Preserve

| # | Strength | Notes |
|---|----------|-------|
| S1 | **Similarity engine is genuinely novel** | Weighted feature scoring + GPS/waypoint multiplicative factor is a thoughtful approach not found in competing products |
| S2 | **PCA visualization is performance-optimized** | Canvas rendering + D3 quadtree for hover detection handles thousands of points well |
| S3 | **Design system is cohesive and premium** | CSS variables, glassmorphism, JetBrains Mono for metrics — this *feels* good |
| S4 | **Data pipeline from notebook is battle-tested** | The `_process_activities()` logic handles messy real-world Strava data well |
| S5 | **Split-level comparison** | 0.1-mile resolution with multi-activity overlay is genuinely useful for runners |

---

## Prioritized Backlog

### 🔴 P0 — Immediate Fixes (Sprint 1-2)

> **Goal:** Ship the app with confidence. Fix anything that can crash or hang production.

---

#### P0-1: Fix Chart Zoom (Drag-to-Zoom on Split Charts)

**User Story:** *As a runner comparing two activities, I want to drag-select a region on the Pace or HR chart to zoom in, so I can see small differences at specific segments.*

**Current State:** Zoom state exists in `ActivityDetail.jsx` (`zoomPace`, `zoomHR`, `dragPace`, `dragHR`), but `ReferenceArea` is not imported and the `getFilteredData` helper has edge cases. A separate `ZoomableContainer.jsx` component exists but is not wired up.

**Tasks:**
- [x] **P0-1a:** ✅ Added `ReferenceArea` to the Recharts import in `ActivityDetail.jsx`
- [x] **P0-1b:** ✅ Replaced inline drag logic with `activeLabel`-based handlers (more reliable than drilling `activePayload`)
- [x] **P0-1c:** ✅ `handleSetXAxisType()` clears all zoom + drag state on axis toggle
- [x] **P0-1d:** ✅ Zoom added to all 4 Dashboard charts (Pace Over Time, Weekly Mileage, HR Trend, Pace vs HR) via `useChartZoom` hook — each chart zooms independently
- [x] **P0-1e:** ✅ Added "drag to zoom" italic hint below chart header; shows "↺ Reset Zoom" button when active
- [x] **P0-1f:** ✅ Global `keydown → Escape` listener resets zoom in both `ActivityDetail` (inline) and all Dashboard charts (via `useChartZoom` hook)

**Acceptance:** ✅ Fully complete — drag-to-zoom works on all charts across Dashboard and ActivityDetail. Escape resets zoom everywhere. Each chart zooms independently.

**Estimate:** 3-5 hours

---

#### P0-2: Add React Error Boundaries

**Tasks:**
- [x] **P0-2a:** ✅ Created `ErrorBoundary.jsx` — class component with compact (chart) and full-page modes
- [x] **P0-2b:** ✅ Wrapped `Dashboard`, `ActivityDetail`, and `SimilarityExplorer` routes in `App.jsx`
- [ ] **P0-2c:** Wrap individual chart components in compact `<ErrorBoundary compact>` — Sprint 4 (component decomposition)
- [x] **P0-2d:** ✅ Both compact and full-page modes include Retry / Go to Dashboard buttons

**Estimate:** 2 hours

---

#### P0-3: Async Sync with Progress Feedback

**Current Problem:** `POST /api/activities/sync` is synchronous and can block the FastAPI server for minutes during a deep sync.

**Tasks:**
- [x] **P0-3a:** ✅ Moved sync execution to a background `threading.Thread` via `start_sync_background()` — POST returns immediately with `{status: 'started'}`
- [x] **P0-3b:** ✅ Added `GET /api/activities/sync/status` endpoint returning `{status, message, fetched, added, skipped, deep, started_at, error}`
- [x] **P0-3c:** ✅ `SyncPanel.jsx` rewritten to poll status every 1.5s with an animated indeterminate progress bar and live "Fetched N…" count label
- [x] **P0-3d:** ✅ Added 10-minute `_SYNC_TIMEOUT_SECONDS = 600` deadline; `TimeoutError` is caught and reported via state machine

**Note:** `SyncPanel` also eliminates `window.location.reload()` with an `onSyncComplete` callback prop for future state-invalidation integration.

---

#### P0-4: Fix CSV Write Contention

**Tasks:**
- [x] **P0-4a:** ✅ Added `threading.Lock` (`self._write_lock`) to `DataService.__init__`
- [x] **P0-4b:** ✅ Added `_safe_csv_write()` static method — writes to `.tmp` then atomically renames into place; cleans up on error
- [ ] **P0-4c:** Queue split fetches so only one `sync_activity_details` runs at a time — tracked in P0-3 (async sync)

**Estimate:** 2 hours

---

#### P0-5: Vectorize Startup Data Processing

**Current Problem:** `_process_activities()` uses row-by-row `for idx, val` loops for lat/lng and polyline parsing (~2,100 iterations with `ast.literal_eval` per row).

**Tasks:**
- [x] **P0-5a:** ✅ Replaced `start_latlng` for-loop with `.apply(_extract_lat)` / `.apply(_extract_lng)`
- [x] **P0-5b:** ✅ Replaced `end_latlng` for-loop with `.apply()` equivalents
- [x] **P0-5c:** ✅ Replaced `map` polyline for-loop with `.apply(self._extract_polyline)`
- [x] **P0-5d:** ✅ Added `_time.perf_counter()` timing in `_load_data()` — startup time logged as `DataService startup complete in Xms`

---

### 🟡 P1 — Architectural Enhancements (Sprint 3-5)

> **Goal:** Set the foundation for scale. These won't be visible to users but will dramatically reduce future engineering friction.

---

#### P1-1: Migrate Storage from CSV to SQLite

**Why:** CSVs are loaded entirely into memory, have write contention issues, and don't support concurrent reads/writes or indexed queries.

**Implementation Note:** This epic is further along than the original roadmap indicated. The codebase now has a SQLite-backed `DataService`, a migration script, query-side indexes, and a `sync_log` table in place. Remaining work is the async/connection-pool story.

**Tasks:**
- [x] **P1-1a:** Design SQLite schema with tables: `activities`, `splits`, `summaries`, `sync_log`
- [x] **P1-1b:** Write a migration script that imports existing CSVs into SQLite
- [x] **P1-1c:** Refactor `DataService` to use SQLite queries instead of pandas DataFrame operations
- [x] **P1-1d:** Keep pandas for analytics-heavy operations (PCA, similarity) but load only what's needed via SQL
- [ ] **P1-1e:** Add database connection pooling (using `aiosqlite` for async compatibility)
- [x] **P1-1f:** Add indexes on `id`, `type`, `date`, `activity_id` (splits)

**Impact:** Eliminates C1 (memory), C6 (write contention), enables server-side pagination, reduces startup to < 100ms

**Estimate:** 8-12 hours

---

#### P1-2: Decompose ActivityDetail into Sub-Components

**Why:** `ActivityDetail.jsx` at 879 lines is the most fragile file in the codebase. Any change (like fixing zoom) requires understanding the entire component.

**Tasks:**
- [x] P1-2: Decompose `ActivityDetail.jsx` into Sub-Components ✅
- [x] P1-2a: Extract `ActivityHeader` ✅
- [x] P1-2b: Extract `PerformanceDelta` ✅
- [x] P1-2c: Extract `FastestSegments` ✅
- [x] P1-2d: Extract `SimilarWorkoutsPanel` ✅
- [x] P1-2e: Extract Detail Charts ✅
- [x] P1-x: Fix Timezone/Date handling (Prefer start_date_local) ✅
- [x] **P1-2g:** Create a shared `useComparisonState` custom hook for the comparison selection logic
- [x] **P1-2h:** Create a shared `useZoomState` custom hook for chart zoom logic

**Impact:** Each component becomes independently testable, reviewable, and modifiable.

**Estimate:** 6-8 hours

---

#### P1-3: Add Frontend State Management

**Why:** Currently, navigating from ActivityDetail back to Dashboard loses all context. Each page fires independent API calls. Comparison state doesn't persist across navigation.

**Implementation Note:** Chose React Context for shared app state and added React Query for API data fetching, cache lifecycle, and background revalidation.

**Tasks:**
- [x] **P1-3a:** Evaluate lightweight state solutions: Zustand (recommended), Jotai, or React Context
- [x] **P1-3b:** Create stores: `useActivityStore` (activities list + cache), `useOverviewStore` (stats), `useComparisonStore` (selected comparison IDs)
- [x] **P1-3c:** Add SWR or React Query for API data fetching with caching and revalidation
- [x] **P1-3d:** Persist comparison selections in URL params so they survive page refresh

**Estimate:** 6-8 hours

---

#### P1-4: Add Backend Caching Layer

**Why:** PCA computation and similarity scoring are expensive. They're recomputed on every single request, even though the underlying data rarely changes.

**Tasks:**
- [x] **P1-4a:** Add `functools.lru_cache` or a TTL cache to `get_activity_pca()` keyed by `(activity_type, data_hash)`
- [x] **P1-4b:** Add caching to `find_similar_activities()` keyed by `(activity_id, top_n)`
- [x] **P1-4c:** Invalidate caches when `add_activities()` or `update_activities()` modifies data
- [x] **P1-4d:** Add a `GET /api/cache/status` endpoint for debugging

**Estimate:** 3-4 hours

---

#### P1-5: Add Pydantic Response Models

**Why:** API currently returns raw dicts. No guarantee of response shape. Frontend can crash on unexpected nulls.

**Tasks:**
- [x] **P1-5a:** ✅ Added `from backend.models import schemas` import to `activities.py`
- [x] **P1-5b:** ✅ `/activities/compare` now accepts a typed `schemas.CompareRequest` body (validates `activity_ids` list; removes raw `body.get()` access)
- [x] **P1-5c:** ✅ `/activities` list endpoint has `response_model=Dict[str, Any]` declared
- [x] **P1-5d:** Add full `response_model` to all remaining endpoints using existing Pydantic schemas — completed March 22, 2026
- [x] **P1-5e:** Add API documentation via OpenAPI (auto-generated once `response_model` is complete)

---

#### P1-6: Testing Foundation

**Tasks:**
- [x] **P1-6a:** Add `pytest` to backend with a test fixture that creates an isolated temporary DataService / SQLite dataset for tests
- [x] **P1-6b:** Write unit tests for: `DataService.get_activities`, `find_similar_activities`, `get_activity_pca`, `StravaAuthService.get_access_token`
- [ ] **P1-6c:** Add Vitest to frontend with component tests for: `formatPace`, `formatDistance`, `ZoomableContainer`
- [x] **P1-6d:** Add a GitHub Actions CI workflow that runs tests on PR

**Estimate:** 8-10 hours

---

### 🟢 P2 — Feature Enhancements (Sprint 5-8)

> **Goal:** Ship the features users are asking for and the ones they don't know they need yet.

---

#### P2-1: Training Load & Fitness Metrics

**User Story:** *As a runner, I want to see my weekly training load and fitness trend over time, so I can make smarter training decisions and avoid overtraining.*

**Concept:** Implement a simple TRIMP (Training Impulse) or TSS-like score for each activity using heart rate and duration. Roll up into weekly load. Show a fitness/fatigue chart inspired by TrainingPeaks' Performance Management Chart (PMC).

**Tasks:**
- [ ] **P2-1a:** Add a `training_load` column to activities (TRIMP: `duration_min * avg_hr * intensity_factor`)
- [ ] **P2-1b:** Backend: `GET /api/stats/training-load` — returns daily/weekly load aggregates
- [ ] **P2-1c:** Frontend: "Training Load" card on Dashboard with sparkline
- [ ] **P2-1d:** Frontend: "Fitness Trend" chart — exponential moving averages for fitness (42-day), fatigue (7-day), and form (fitness - fatigue)

**Why This Matters:** This is the #1 feature in premium training platforms (TrainingPeaks, Strava Summit). Implementing it with locally-computed data using the Strava API streams we already have would be a major differentiator for a free tool.

**Estimate:** 10-14 hours

---

#### P2-2: Automated Insights Engine

**User Story:** *As a runner, I want the app to proactively tell me when I've hit a PR, broken a streak, or am trending faster on a route—without me having to manually investigate.*

**Tasks:**
- [ ] **P2-2a:** Backend: `InsightsService` that runs after each sync and checks for:
  - New personal records at key distances (1mi, 5K, 10K, half, full)
  - Pace improvement on a route cluster (>3% faster than cluster average)
  - Heart rate efficiency improvement (same pace, lower HR)
  - Consistency streaks (X consecutive weeks with Y+ activities)
  - Sudden training load spikes (potential injury risk signal)
- [ ] **P2-2b:** Backend: `GET /api/insights` — returns a prioritized list of recent insights
- [ ] **P2-2c:** Backend: Store insights in an `insights` table so they persist
- [ ] **P2-2d:** Frontend: Insights panel on Dashboard — dismissable cards with contextual links
- [ ] **P2-2e:** Frontend: Insight badges on Activity Detail ("This was a 5K PR!" banner)

**Estimate:** 12-16 hours

---

#### P2-3: Route Clusters / Route Library

**User Story:** *As a runner with 500+ runs, I want the app to automatically group my activities by route, so I can see all my "morning neighborhood loop" runs in one place and track progress on that specific route.*

**Tasks:**
- [ ] **P2-3a:** Backend: `ClusterService` using DBSCAN on GPS waypoints to auto-detect route families
- [ ] **P2-3b:** Backend: `GET /api/clusters` — list all route clusters with member count, avg pace, map preview
- [ ] **P2-3c:** Backend: `GET /api/clusters/{id}/activities` — activities within a cluster
- [ ] **P2-3d:** Frontend: Route Library page — grid of route cards showing map thumbnail, stats, member count
- [ ] **P2-3e:** Frontend: Cluster Detail page — performance chart across all runs on that route
- [ ] **P2-3f:** Allow users to name/rename clusters
- [ ] **P2-3g:** "Suggest Merge" — detect clusters that might be the same route (e.g., clockwise vs counterclockwise)

**Estimate:** 14-18 hours

---

#### P2-4: Advanced Chart Interactions

**Beyond basic zoom — make charts a first-class interactive experience.**

**Tasks:**
- [ ] **P2-4a:** **Brush & Link:** Selecting a region on the Pace chart highlights the same segment on the HR chart and the map
- [ ] **P2-4b:** **Tooltip Sync:** Hovering on one chart shows a synchronized crosshair on all peer charts
- [ ] **P2-4c:** **Chart Annotations:** Click on a chart point to add a note ("hill starts here", "stopped for water")
- [ ] **P2-4d:** **Export:** Download chart as PNG or SVG
- [ ] **P2-4e:** **Fullscreen Mode:** Expand any chart to full window for deep analysis

**Estimate:** 10-14 hours

---

#### P2-5: Mobile-Responsive Layout

**Tasks:**
- [ ] **P2-5a:** Audit all pages on 375px viewport — fix any horizontal overflow
- [ ] **P2-5b:** Convert Dashboard grid to stack layout on mobile
- [ ] **P2-5c:** Convert ActivityDetail to single-column layout on mobile
- [ ] **P2-5d:** Make charts touch-friendly: pinch-to-zoom, swipe to pan
- [ ] **P2-5e:** Bottom navigation bar on mobile (Dashboard / Activity / Explore)
- [ ] **P2-5f:** Add PWA manifest for "Add to Home Screen" capability

**Estimate:** 8-12 hours

---

### 🔵 P3 — Strategic Innovation (Sprint 8-12+)

> **Goal:** Features that fundamentally differentiate Workout Viz from Strava and competing platforms.

---

#### P3-1: "Effort Score" — A Universal Performance Metric

**Concept:** Create a single composite score for each activity that accounts for pace, heart rate, elevation, and conditions. Think of it as "GAP (Grade Adjusted Pace)" meets "Running Power" but computed entirely from the data we already have.

**Why:** Strava's "Relative Effort" requires a heart rate monitor and uses opaque algorithms. Our version would be transparent, customizable, and work even without HR data.

**Tasks:**
- [ ] **P3-1a:** Design the effort score formula: `f(pace_normalized, hr_normalized, elevation_factor, distance_factor)`
- [ ] **P3-1b:** Compute for all activities; expose via API
- [ ] **P3-1c:** Add to activity cards, charts, and comparisons
- [ ] **P3-1d:** Allow users to adjust weights (value pace vs HR vs elevation)

**Estimate:** 6-8 hours

---

#### P3-2: AI Training Narrative

**Concept:** Use an LLM to generate natural-language summaries of training patterns. "You've been running 25% more this month but your pace has plateaued. Your heart rate efficiency on your usual 5K loop has improved by 8% since January."

**Tasks:**
- [ ] **P3-2a:** Backend: `NarrativeService` that aggregates stats into a structured prompt
- [ ] **P3-2b:** Integrate with a local LLM (Ollama) or API-based LLM (OpenAI/Anthropic)
- [ ] **P3-2c:** Frontend: "Weekly Summary" card on Dashboard with generated text
- [ ] **P3-2d:** Frontend: "Training Insights" chat-like interface for natural language queries

**Estimate:** 8-12 hours

---

#### P3-3: Social Comparison (Anonymized)

**Concept:** For users who opt in, provide anonymized percentile rankings. "Your 5K pace is in the top 25% of runners in your age group who run similar routes."

**Tasks:**
- [ ] **P3-3a:** Design privacy-first architecture (aggregate only, no raw data sharing)
- [ ] **P3-3b:** Backend: percentile computation service
- [ ] **P3-3c:** Frontend: percentile badges and distribution charts

**Estimate:** 10-14 hours

---

#### P3-4: Containerized Deployment

**Tasks:**
- [ ] **P3-4a:** Create `Dockerfile` for backend (FastAPI + Uvicorn)
- [ ] **P3-4b:** Create `Dockerfile` for frontend (Vite build → Nginx)
- [ ] **P3-4c:** Create `docker-compose.yml` for full-stack local dev
- [ ] **P3-4d:** Add health checks and graceful shutdown
- [ ] **P3-4e:** Optionally: deploy to a VPS or cloud provider (Fly.io, Railway, or self-hosted)

**Estimate:** 4-6 hours

---

## Priority Matrix

```
                        HIGH IMPACT
                            │
         P0-1 Chart Zoom   │   P2-1 Training Load
         P0-3 Async Sync   │   P2-2 Insights Engine
         P0-2 Error Bounds  │   P2-3 Route Clusters
                            │   P3-1 Effort Score
    ────────────────────────┼────────────────────────
                            │
         P0-4 CSV Safety    │   P2-4 Chart Interactions
         P0-5 Perf Startup  │   P2-5 Mobile Layout
         P1-5 Pydantic      │   P3-2 AI Narrative
         P1-4 Caching       │   P3-3 Social
                            │
                        LOW IMPACT

    LOW EFFORT ─────────────────────────── HIGH EFFORT
```

## Sprint Plan (Suggested)

| Sprint | Focus | Key Deliverables |
|--------|-------|-----------------|
| **Sprint 1** ✅ | 🔴 Stability | ~~P0-1 (Chart Zoom)~~, ~~P0-2 (Error Boundaries)~~, ~~P0-4 (CSV Safety)~~ — **DONE** |
| **Sprint 2** ✅ | 🔴 Reliability | ~~P0-3 (Async Sync)~~, ~~P0-5 (Startup Perf)~~, ~~P1-5 (Pydantic/typed requests)~~ — **DONE** |
| **Sprint 3** ✅ | 🟡 Architecture | ~~P1-1 (SQLite Migration)~~, ~~P1-4 (TTL Caching)~~ — **DONE** |
| **Sprint 4** (Now) | 🟡 Code Quality | ~~P1-2 (Decompose ActivityDetail)~~, P1-3 (State Management) |
| **Sprint 5** | 🟡 Quality | P1-6 (Testing Foundation) |
| **Sprint 6-7** | 🟢 Features | P2-1 (Training Load), P2-2 (Insights Engine) |
| **Sprint 8-9** | 🟢 Features | P2-3 (Route Clusters), P2-4 (Chart Interactions) |
| **Sprint 10** | 🟢 Reach | P2-5 (Mobile), P3-4 (Docker) |
| **Sprint 11-12** | 🔵 Innovation | P3-1 (Effort Score), P3-2 (AI Narrative) |

---

## Architecture Target State

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (Vite + React)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐│
│  │Dashboard │  │Activity  │  │Similarity│  │  Route Library   ││
│  │+ Insights│  │Detail    │  │Explorer  │  │  (NEW)           ││
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘│
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  Zustand Store + React Query (caching, revalidation)        ││
│  └──────────────────────────────────────────────────────────────┘│
│          ↕              ↕               ↕              ↕         │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │             REST API (FastAPI + Pydantic v2)                ││
│  │             + Response Models + Caching Layer               ││
│  └──────────────────────────────────────────────────────────────┘│
│          ↕              ↕               ↕              ↕         │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐  ┌─────────────┐│
│  │  Strava  │  │ Insights  │  │  Similarity  │  │  Training   ││
│  │  OAuth   │  │ Engine    │  │  + Clusters   │  │  Load Calc  ││
│  │  + Sync  │  │ (NEW)     │  │  + PCA       │  │  (NEW)      ││
│  └──────────┘  └───────────┘  └──────────────┘  └─────────────┘│
│          ↕              ↕               ↕              ↕         │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │              SQLite + Connection Pool                        ││
│  │       (activities, splits, summaries, insights, clusters)    ││
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix: File-Level Audit

| File | Lines | Health | Notes |
|------|-------|--------|-------|
| `backend/main.py` | 50 | 🟢 | Clean, minimal. CORS needs parameterization. |
| `backend/api/activities.py` | 171 | 🟢 | Well-structured. Add response_model. |
| `backend/api/auth.py` | 55 | 🟡 | `status` endpoint accesses `_activities_df` directly — breaks abstraction. |
| `backend/services/data_service.py` | 590 | 🟡 | ✅ `threading.Lock` + atomic writes added. Row-by-row loops remain (P0-5). Needs SQLite (P1-1). |
| `backend/services/sync_service.py` | 351 | 🟡 | Synchronous Strava API calls block server. Needs async (P0-3). |
| `backend/services/similarity_service.py` | 200 | 🟢 | Well-designed. Needs caching. |
| `backend/services/pca_service.py` | 109 | 🟢 | Clean. Needs caching + DBSCAN option. |
| `backend/services/strava_auth.py` | 138 | 🟢 | Solid token management. |
| `backend/models/schemas.py` | 103 | 🟡 | Schemas exist but aren't used as response_models. |
| `frontend/src/pages/Dashboard.jsx` | 423 | 🟡 | Manageable but charts have no zoom capability (P0-1d). |
| `frontend/src/pages/ActivityDetail.jsx` | 895 | 🟡 | ✅ Zoom fixed. God Component — decompose in P1-2. |
| `frontend/src/pages/SimilarityExplorer.jsx` | 226 | 🟢 | Well-structured. |
| `frontend/src/components/WorkoutPCA.jsx` | 446 | 🟢 | Canvas + D3 is a smart approach. |
| `frontend/src/components/ZoomableContainer.jsx` | 188 | 🟡 | Built but unused. Wire in during P1-2 component decomposition. |
| `frontend/src/components/ErrorBoundary.jsx` | 143 | 🟢 | ✅ New — compact + full-page modes, Retry button. |
| `frontend/src/components/ProgressTimeline.jsx` | 131 | 🟢 | Clean and focused. |
| `frontend/src/components/SyncPanel.jsx` | 126 | 🟡 | Uses `window.location.reload()` after sync — should use state invalidation. |
| `frontend/src/App.jsx` | 53 | 🟢 | ✅ All routes wrapped in ErrorBoundary. |
| `frontend/src/utils/api.js` | 78 | 🟡 | No error handling beyond status code. No retry. No cancellation. |
| `frontend/src/utils/format.js` | 119 | 🟢 | Solid utility functions. |
| `frontend/src/index.css` | 1092 | 🟢 | Comprehensive design system. Well-organized. |

---

> **This roadmap is a living document.** As we ship each sprint, we'll update priorities based on user feedback and technical discoveries. The goal is not to build everything — it's to build the right things in the right order so that each sprint compounds the value of the last.
