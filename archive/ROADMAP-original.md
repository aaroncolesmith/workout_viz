# 🏃 Workout Viz — Product & Engineering Roadmap

> **Vision**: A personal fitness analytics platform that automatically groups similar workouts, visualizes performance trends over time, and surfaces insights about your progress — turning raw Strava data into actionable training intelligence.

---

## 📐 Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Vite + React)               │
│  ┌──────────┐  ┌───────────┐  ┌───────────────────────┐ │
│  │ Dashboard │  │ Activity  │  │  Similarity Explorer  │ │
│  │ Overview  │  │  Detail   │  │  (Radar / Comparison) │ │
│  └──────────┘  └───────────┘  └───────────────────────┘ │
│          ↕              ↕               ↕                │
│  ┌──────────────────────────────────────────────────────┐│
│  │               REST API (FastAPI)                     ││
│  └──────────────────────────────────────────────────────┘│
│          ↕              ↕               ↕                │
│  ┌──────────┐  ┌───────────┐  ┌───────────────────────┐ │
│  │  Strava  │  │ Data Proc │  │  Similarity Engine    │ │
│  │  OAuth   │  │ Pipeline  │  │  (Cosine / Clusters)  │ │
│  └──────────┘  └───────────┘  └───────────────────────┘ │
│          ↕              ↕               ↕                │
│  ┌──────────────────────────────────────────────────────┐│
│  │            Storage (CSV / Parquet / SQLite)           ││
│  └──────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

---

## 🗂️ Data Model (Existing Assets)

Your notebook has already established three core datasets. The app will productionize these:

| Dataset | File | Key Columns | Records |
|---------|------|-------------|---------|
| **Activities** | `strava_activities.csv` | `id`, `name`, `type`, `sport_type`, `distance_miles`, `elapsed_time_min`, `moving_time_min`, `average_speed`, `average_heartrate`, `max_heartrate`, `total_elevation_gain`, `start_latlng`, `end_latlng`, `start_date`, `pace` | ~2,130 |
| **Splits** | `strava_splits.csv` | `activity_id`, `0.1_mile`, `time_seconds`, `avg_heartrate`, `max_heartrate`, `elevation_gain_meters`, `rolling_*_mile_seconds` | ~7,260 |
| **Summary** | `strava_summary.csv` | `activity_id`, `activity_name`, `distance_miles`, `fastest_time_seconds`, `avg_heartrate_fastest`, `elevation_gain_fastest_meters` | ~560 |

---

## 🏗️ Phase 1: Foundation & Data Layer
**Goal**: Productionize the notebook's data pipeline into a backend API with structured storage.

### Epic 1.1: Project Scaffolding
- [x] **Task 1.1.1**: Initialize Vite + React frontend (`npx -y create-vite@latest ./frontend`) ✅
- [x] **Task 1.1.2**: Initialize FastAPI backend (`backend/`) with virtual environment ✅
- [x] **Task 1.1.3**: Set up project structure ✅
  ```
  workout_viz/
  ├── frontend/          # Vite + React
  │   ├── src/
  │   │   ├── components/
  │   │   ├── pages/
  │   │   └── utils/
  │   └── ...
  ├── backend/           # FastAPI
  │   ├── api/           # Route handlers
  │   ├── services/      # Business logic
  │   ├── models/        # Data models / schemas
  │   └── data/          # CSV/Parquet storage
  ├── data/              # Raw + processed data files
  └── ROADMAP.md
  ```
- [ ] **Task 1.1.4**: Docker Compose for local dev (FastAPI + Vite dev server)

### Epic 1.2: Strava OAuth Integration
- [x] **Task 1.2.1**: Backend Auth Service — token exchange, refresh, and secure storage logic ✅
- [/] **Task 1.2.2**: Auth API endpoints — `/auth/status`, `/auth/strava/url`, `/auth/strava/callback` (Implemented) ⏳
- [/] **Task 1.2.3**: React Auth flow — `AuthCallback` route and Strava "Connect" button in UI (Implemented) ⏳

### Epic 1.3: Live Data Sync Engine
- [/] **Task 1.3.1**: Sync service — fetch new activities from Strava API based on last synced date (Implemented) ⏳
- [ ] **Task 1.3.2**: Rate limit handling — implement Strava's 15min/daily limit awareness
- [ ] **Task 1.3.3**: Sync progress UI — real-time feedback during large data pulls (e.g., historical backfills)
- [ ] **Task 1.3.4**: Data backfill validator — scan CSV for activities missing splits/summaries, selectively re-fetch

### Epic 1.4: Multi-Server Dev Environment
- [x] **Task 1.4.1**: Create unified `start.sh` — manage FastAPI + Vite concurrent processes ✅
- [x] **Task 1.4.2**: API Proxy configuration — ensure seamless frontend/backend communication ✅
- [ ] **Task 1.4.3**: Docker Compose for production-like local dev

### Epic 1.5: API Endpoints (v1)
- [x] **Task 1.5.1**: `GET /api/activities` — list activities with filters (type, date range, distance range) ✅
- [x] **Task 1.5.2**: `GET /api/activities/{id}` — full activity detail with map polyline, GPS coords ✅
- [x] **Task 1.5.3**: `GET /api/activities/{id}/splits` — detailed 0.1-mile splits for an activity ✅
- [x] **Task 1.5.4**: `POST /api/activities/sync` — trigger a data sync from Strava ✅
- [x] **Task 1.5.5**: `GET /api/stats/overview` — aggregated stats (total miles, total time, activity counts by type) ✅
- [x] **Task 1.5.6**: `GET /api/stats/trends` — time-series trend data for charts ✅
- [x] **Task 1.5.7**: `GET /api/stats/calendar` — activity heatmap aggregates ✅
- [x] **Task 1.5.8**: `GET /api/activities/{id}/similar` — find similar activities via cosine similarity ✅
- [x] **Task 1.5.9**: `POST /api/activities/compare` — multi-activity comparison ✅
- [x] **Task 1.5.10**: `GET /api/activities/{id}/summary` — fastest segment summaries ✅


---

## 📊 Phase 2: Core Visualizations
**Goal**: Build the primary visualization layer — dashboard overview and activity detail views.

### Epic 2.1: Dashboard Overview Page
- [x] **Task 2.1.1**: Activity feed — paginated list of workouts with type icons, distance, pace, heart rate badges ✅
- [x] **Task 2.1.2**: Summary stat cards — total miles (10,120), total activities (2,128), avg pace (8:16), avg HR (141) ✅
- [x] **Task 2.1.3**: Activity calendar heatmap — GitHub-style contribution chart showing workout frequency and intensity ✅
- [x] **Task 2.1.4**: Activity type distribution — donut chart showing Run vs Ride vs Hike breakdown ✅
- [x] **Task 2.1.5**: Activity type filter (global filter bar with counts) ✅

### Epic 2.2: Trend Charts
- [x] **Task 2.2.1**: Pace over time — scatter plot colored by activity type ✅
- [x] **Task 2.2.2**: Heart rate over time — avg HR scatter colored by type ✅
- [x] **Task 2.2.3**: Distance over time — weekly mileage bar chart (last 6 months) ✅
- [x] **Task 2.2.4**: Pace vs Heart Rate scatter — efficiency visualization ✅

### Epic 2.3: Activity Detail Page
- [x] **Task 2.3.1**: Activity header — name, date, type badge, stat cards (distance, duration, pace, HR, elevation, cadence, power) ✅
- [x] **Task 2.3.2**: Fastest segments table — distance, time, avg HR, segment range ✅
- [x] **Task 2.3.3**: Split pace area chart — pace per 0.1-mile split with gradient fill ✅
- [x] **Task 2.3.4**: Heart rate per split chart — avg HR area with max HR dashed overlay ✅
- [x] **Task 2.3.5**: Map view — render `summary_polyline` on interactive Leaflet map (CartoDB Dark Matter tiles, route glow effect, start/end markers) ✅
- [x] **Task 2.3.6**: Similar Workouts panel — top 5 similar activities with match % badges ✅ _(bonus)_

---

## 🔍 Phase 3: Similarity Engine
**Goal**: The core differentiator — use the cosine similarity approach from NBA Aaronlytics to find and compare "similar" workouts.

### Epic 3.1: Defining "Similar" Workouts

A workout's **similarity vector** is constructed from these normalized attributes:

| Attribute | Weight | Rationale |
|-----------|--------|-----------|
| `type` / `sport_type` | **Must match** | Runs ≠ Rides ≠ Hikes — filter first |
| `distance_miles` | High | Core route-matching signal |
| `total_elevation_gain` | Medium | Flat runs ≠ hilly runs |
| `start_latlng` proximity | High | Same neighborhood = same route |
| `end_latlng` proximity | Medium | Confirms loop vs point-to-point |
| **Route waypoints** (25%, 50%, 75%) | **High** | Confirms same route path — start/end alone is insufficient for loops |
| `average_cadence` | Low | Effort similarity signal |

- [x] **Task 3.1.1**: Implement similarity vector builder (Overhauled: Multiplicative weighted scoring) ✅
- [x] **Task 3.1.2**: GPS proximity scoring (Refined: 0.7-1.0x Multiplicative factor) ✅
- [x] **Task 3.1.2b**: Route waypoint matching (Refined: 0.7-1.0x Multiplicative factor) ✅
- [ ] **Task 3.1.3**: Pre-compute similarity matrix per activity type (Run, Ride, Hike)
- [ ] **Task 3.1.4**: Clustering with DBSCAN or hierarchical clustering to auto-group "route families"

### Epic 3.2: Similarity API
- [x] **Task 3.2.1**: `GET /api/activities/{id}/similar` — return top-N most similar activities with similarity score ✅
- [ ] **Task 3.2.2**: `GET /api/clusters` — return auto-detected route clusters
- [ ] **Task 3.2.3**: `GET /api/clusters/{cluster_id}/trend` — performance trend within a cluster
- [x] **Task 3.2.4**: `POST /api/activities/compare` — custom multi-activity comparison ✅

### Epic 3.3: Route Groups / Clusters UI
- [ ] **Task 3.3.1**: Route cluster cards — show grouped workouts with shared map overlay, count, avg pace
- [x] **Task 3.3.2**: "Similar to this" panel on Activity Detail page — show top 5 most similar workouts ✅
- [ ] **Task 3.3.3**: Cluster naming — allow user to name clusters ("Morning neighborhood loop", "Forest Park long run")

---

## 🕸️ Phase 4: Radar Charts & Comparison Views
**Goal**: Port the NBA Aaronlytics `RadarStats` component pattern to compare workouts visually.

### Epic 4.1: Workout Radar Chart Component
> Adapt the NBA `RadarStats` pattern: normalize metrics, render radar polygons, overlay multiple workouts.

- [x] **Task 4.1.1**: Define radar attributes for workouts ✅
- [x] **Task 4.1.2**: Port `RadarStats.jsx` component: normalize metrics, multi-workout overlay ✅
- [ ] **Task 4.1.3**: Selectable radar attributes — let users toggle which metrics appear on the radar
- [x] **Task 4.1.4**: Glassmorphism styling to match the NBA Aaronlytics premium aesthetic ✅

### Epic 4.2: Side-by-Side Comparison View
- [x] **Task 4.2.1**: Comparison view — overlay similar workouts on the radar chart ✅
- [x] **Task 4.2.2**: Radar overlay — all selected workouts on one chart ✅
- [x] **Task 4.2.3**: Split-by-split overlay line chart — pace per split for each compared workout ✅
- [x] **Task 4.2.4**: Heart rate overlay — HR curve per split for each workout ✅
- [x] **Task 4.2.5**: Delta table — show improvement/regression per metric vs previous similar workout ✅

### Epic 4.3: Progress Timeline
- [x] **Task 4.3.1**: For a route cluster, show radar charts in chronological sequence (carousel or filmstrip) ✅
- [x] **Task 4.3.2**: Animated radar — smooth morph between workout radar shapes to show progression ✅
- [x] **Task 4.3.3**: Progress score — single numeric score representing overall fitness delta across a cluster ✅

---

## 📈 Phase 5: Insights & Intelligence
**Goal**: Surface actionable training insights automatically.

### Epic 5.1: Automated Insights
- [ ] **Task 5.1.1**: "Getting Faster" detector — flag when pace is trending down within a route cluster
- [ ] **Task 5.1.2**: "Heart Rate Efficiency" — flag when avg HR is decreasing at same or better pace
- [ ] **Task 5.1.3**: "New PR" alerts — detect personal records at various distances (1mi, 5K, 10K, half)
- [ ] **Task 5.1.4**: "Consistency" tracker — streak tracking for workout frequency

### Epic 5.2: Advanced Analytics
- [ ] **Task 5.2.1**: Pace distribution — histogram of mile paces across all activities
- [ ] **Task 5.2.2**: Elevation impact analysis — correlation between elevation gain and pace delta
- [ ] **Task 5.2.3**: Time-of-day performance — do you run faster in the morning vs evening?
- [ ] **Task 5.2.4**: Indoor vs Outdoor comparison — treadmill performance vs real-world

---

## 🎨 Phase 6: Design System & Polish
**Goal**: Premium, data-dense UI that feels alive.

### Epic 6.1: Design Foundation
- [x] **Task 6.1.1**: Dark theme with rich gradients (deep navy → midnight purple) ✅
- [x] **Task 6.1.2**: Typography: Inter for body, JetBrains Mono for metrics/numbers ✅
- [x] **Task 6.1.3**: Color palette for activity types ✅:
  - 🏃 Run: `#38bdf8` (sky blue)
  - 🚴 Ride: `#818cf8` (indigo)
  - 🥾 Hike: `#34d399` (emerald)
  - ❤️ Heart Rate: `#f472b6` → `#ef4444` (gradient pink to red)
- [x] **Task 6.1.4**: Glassmorphism cards with subtle backdrop blur ✅
- [x] **Task 6.1.5**: Micro-animations: hover transitions, row lift effects, smooth scrollbar ✅

### Epic 6.2: Responsive & Accessible
- [ ] **Task 6.2.1**: Mobile-first layout for on-the-go review
- [ ] **Task 6.2.2**: Chart touch interactions (pinch-zoom on split charts)
- [ ] **Task 6.2.3**: Accessible color contrast, screen reader labels, keyboard navigation

---

## 🚀 MVP Definition (Phases 1-2 + Partial Phase 3)

The **Minimum Viable Product** delivers:

1. ✅ Strava OAuth login + automatic data sync
2. ✅ Dashboard with activity feed, trend charts, calendar heatmap
3. ✅ Activity detail page with splits and map
4. ✅ Basic similarity — find top 5 "most similar" workouts to any given activity
5. ✅ Single radar chart comparison between 2 workouts

### MVP User Story
> *"As a runner, I want to select my last run and instantly see the 5 most similar past runs, compare my pace and heart rate on a radar chart, and see if I'm getting faster on this route."*

---

## 🔧 Tech Stack Summary

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Frontend** | Vite + React | Fast DX, lightweight |
| **Charts** | Recharts | Radar chart component already proven in NBA project |
| **Maps** | Leaflet + react-leaflet | Free, excellent polyline support |
| **Styling** | Vanilla CSS (design system) | Full control, premium aesthetics |
| **Backend** | FastAPI (Python) | Keeps alignment with pandas/sklearn pipeline |
| **Data Science** | pandas, scikit-learn, numpy | Similarity engine, data transforms |
| **Storage** | Parquet (or SQLite for v2) | Columnar, fast analytics reads |
| **Auth** | Strava OAuth2 | Native integration |

---

## 📋 Priority Order

| Priority | Phase | Effort | Impact |
|----------|-------|--------|--------|
| **P0** | 1.2 — Strava OAuth | Medium | Unlocks everything |
| **P0** | 1.3 — Data Pipeline | High | Unlocks everything |
| **P0** | 1.4 — API Endpoints | Medium | Unlocks frontend |
| **P1** | 2.1 — Dashboard | Medium | First impression |
| **P1** | 2.2 — Trend Charts | Medium | Core value |
| **P1** | 2.3 — Activity Detail | Medium | Core value |
| **P2** | 3.1 — Similarity Engine | High | Key differentiator |
| **P2** | 3.2 — Similarity API | Medium | Unlocks comparison |
| **P2** | 4.1 — Radar Charts | Medium | Visual wow factor |
| **P3** | 3.3 — Route Clusters | Medium | Power user feature |
| **P3** | 4.2 — Comparison View | Medium | Full comparison UX |
| **P3** | 4.3 — Progress Timeline | Low | Polish |
| **P4** | 5.x — Insights | Medium | Nice to have |
| **P4** | 6.x — Design Polish | Ongoing | Continuous |

---

## 🔗 Cross-References

- **Strava Notebook**: `~/Code/notebooks/strava/strava_notebook.ipynb` — source data pipeline and processing logic
- **NBA Aaronlytics RadarStats**: `~/Code/nba_aaronlytics/frontend/src/components/RadarStats.jsx` — radar chart pattern to adapt
- **NBA Roadmap**: `~/Code/nba_aaronlytics/NBA_VIZ_AI_ROADMAP.md` — roadmap format inspiration
- **Existing Data Files**:
  - `strava_activities.csv` (~2,130 activities, 2015-2026)
  - `strava_splits.csv` (~7,260 splits)
  - `strava_summary.csv` (~560 records)
  - `running_overview.csv` (26 recent runs with curated fields)
