# CPO Product Strategy Brief: Workout Viz

> **Audience**: Engineering team  
> **Date**: 2026-04-13 (last updated 2026-04-17)
> **Session model**: Engineering tasks run in the main session. Design/UI tasks run in a dedicated **Designer Session** (starts fresh, loads Stitch MCP + DESIGN.md, pulls screen code directly from the Stitch project).
> **Purpose**: Define the product path from functional analytics tool to market-leading workout intelligence platform.

## Implementation Status

| Feature | Phase | Status | Notes |
|---|---|---|---|
| Fitness & Fatigue Model (CTL/ATL/TSB) | 1 P0 | ✅ **Done** | `fitness_service.py`, `GET /api/stats/fitness`, `GET /api/stats/readiness`, `FitnessChart.jsx` on dashboard |
| PR Detection | 1 P1 | ✅ **Done** | `pr_events` table, `detect_prs_for_activity()` in DataService, `GET /api/activities/prs`, PR banner on dashboard |
| Post-Workout Insight Card | 1 P0 | ✅ **Done** | `insight_service.py`, `GET /api/activities/:id/insights`, `InsightCard.jsx` in Overview tab |
| Activity Detail Redesign (tabs) | 1 P1 | ✅ **Done** | 4 tabs: Overview / Splits / Compare / Segments; URL-linked via `?tab=` |
| Morning Readiness Card | Opp B | ✅ **Done** | `ReadinessCard.jsx` above stat cards; score + zone + CTL/ATL/TSB |
| Training Block Analysis | 2 P0 | ✅ **Done** | `training_blocks` table, `/api/blocks` CRUD, `TrainingBlocks.jsx` on dashboard with timeline + block cards + block-over-block deltas |
| "Why Was This Workout Good/Bad?" | 2 P0 | ✅ **Done** | Shipped as InsightCard (template-based, same outcome) |
| Race Predictor | 2 P1 | ✅ **Done** | `race_predictor_service.py`, `GET /api/stats/predictions`, `RacePredictor.jsx` on dashboard; Riegel formula + form adjustment + confidence band |
| Route Intelligence | Opp A | ✅ **Done** | `route_service.py`, greedy GPS clustering, `GET /api/routes`, `RoutesPage.jsx`; pace trend, sparklines, mini maps |
| **Apple Health Import (XML)** | **SA-1** | ✅ **Done** | Two-pass iterparse, background thread, negative hash IDs, dedup vs Strava; `POST /api/import/apple-health`, 🍎 button in nav |
| **Strength Training Support** | **SA-2** | ⬜ Next up | Proper detail view for strength/HIIT/yoga (no splits/map); HR-over-time chart; correct activity type badges |
| **Swimming Analytics** | **SA-3** | ⬜ Backlog | SWOLF, pace/100m, lap breakdown (`swim_laps` table); swim-specific detail view |
| **HealthKit Direct Sync** | **SA-4** | ⬜ Backlog — Designer Session dependency | Swift menu bar companion app; HealthKit entitlement; incremental sync to `POST /api/import/healthkit`; eliminates XML export flow |
| **Premium Redesign** | **UX-1** | ⬜ Backlog — **Designer Session** | Stitch MCP loaded; pull screen code for Dashboard + Activity Detail; apply DESIGN.md token system (Manrope/Inter, monochrome surfaces, no-line rule) |
| Training Narrative | Opp C | ⬜ Backlog | Season review; "Spotify Wrapped" for athletes; richer once strength + swim data in |
| Shareable Workout Reports | 2 P1 | ⬜ Backlog | Frontend-only `html2canvas` capture; share a workout comparison or stat card |
| Auto-rebuild routes on sync | Infra | ⬜ Backlog | Trigger route re-cluster after Apple Health import or Strava sync adds new activities |
| Similarity Explorer cluster labels | UX | ⬜ Backlog | "Easy runs", "Tempo", "Long runs" derived from centroid analysis; makes PCA page answer a clear question |

---

## Table of Contents

- [1. Product Audit](#1-product-audit)
  - [Current Feature Inventory](#current-feature-inventory)
  - [High-Value Areas](#high-value-areas)
  - [Value Leaks](#value-leaks)
- [2. Strategic Roadmap](#2-strategic-roadmap)
  - [Phase 1 — Value Validation (Weeks 1-4)](#phase-1--value-validation-weeks-14)
  - [Phase 2 — Differentiators (Weeks 5-12)](#phase-2--differentiators-weeks-512)
  - [Phase 3 — Expansion (Months 4-12)](#phase-3--expansion-months-412)
- [3. High-Impact Opportunities](#3-high-impact-opportunities)
- [4. Engineering Notes](#4-engineering-notes)

---

## 1. Product Audit

### Current Feature Inventory

The product is a single-user workout analytics platform that ingests Strava data into a local SQLite database and surfaces insights across four pages.

#### Dashboard (`/`)
- **5 stat cards**: total activities, distance (mi), time (hrs), avg pace (runs), avg HR
- **Activity calendar**: 52-week GitHub-style heatmap (daily miles/count/minutes)
- **Type distribution**: pie/donut chart with count + percentage per activity type
- **Best segments trend**: scatter + top-10 bar chart for standard distances (1mi, 2mi, 5K, 5mi, 10K, half, full marathon); top 3 highlighted; zoomable
- **Performance charts** (2x2 grid): pace over time, weekly mileage (26 weeks), HR trend, pace vs HR correlation
- **Activity list**: paginated (2,500/page), filterable by time period (all/2yr/1yr/6mo/3mo) and activity type
- **Sync panel**: Strava auth status, incremental + deep sync buttons, progress bar, gap detection

#### Activity Detail (`/activity/:id`)
- **Header**: type badge, name, date, sport type, indoor indicator, 8 stat cards (distance, duration, pace, avg/max HR, elevation, cadence, power)
- **Route map**: Leaflet with decoded polyline, comparison overlays, start/end markers, dark CARTO tiles
- **Radar chart**: 6-axis profile (distance, pace, elevation, HR, duration, cadence); updates with comparisons
- **Performance delta table**: pace/HR/cadence/distance/elevation diffs with color-coded improvement indicators (only shown during comparison)
- **Progress timeline**: horizontal scroll of mini radars for similar activities (>70% match), with pace/efficiency improvement scores
- **Split charts** (side-by-side): pace area chart + HR area chart, 0.1-mile granularity, x-axis toggle (distance vs time), supports up to 5 comparison overlays, "Fetch Missing Data" button for on-demand split sync
- **Fastest segments table** (runs only): standard distances with time/pace/HR/segment range, comparison columns with pace diff highlighting
- **Similar workouts panel**: mini PCA scatter, date filter presets, scrollable list with match breakdown pills (pace/dist/HR/route %), similarity score badges, compare toggles (max 5)

#### Similarity Explorer (`/similarity`)
- **PCA scatter plot**: canvas-rendered (handles thousands of points), K-means colored clusters (k=5), d3 zoom/pan, quadtree hover, feature loading vectors toggle, search box
- **Radar profile tab**: selected activity vs top 5 similar, grid of preview cards
- **Sidebar**: view mode selector, selected activity card with "View Details" link, data info panel
- **Type switcher**: Runs / Rides / Hikes

#### Auth Callback (`/auth/callback`)
- OAuth code exchange with Strava, loading state, success redirect, error handling

### Backend Analytics Stack

| Service | What It Does | Implementation |
|---|---|---|
| **DataService** | Central data access, SQLite reads, caching layer | TTL cache: 5min (PCA/similarity), 2min (trends/calendar), 1min (overview); auto-invalidates on writes |
| **SimilarityService** | Weighted feature matching with route comparison | L1 distance on normalized features: distance 35%, pace 30%, HR 15%, elevation 10%, duration 10%; polyline haversine route multiplier (0.7x-1.0x) |
| **PCAService** | Workout clustering and dimensionality reduction | StandardScaler -> PCA(2) -> KMeans(k=min(5,n)); features: distance, pace, HR, elevation, moving time, cadence |
| **SyncService** | Background Strava ingestion | Thread-based, incremental or deep mode, 10min timeout, thread-safe status polling |

### High-Value Areas

These are the features that deliver genuine differentiation. Protect and invest in them.

| Feature | Why It Matters |
|---|---|
| **Split-level workout comparison (up to 5)** | No consumer app lets you overlay 5 workouts' pace/HR splits on one chart with similarity-scored matching. This is unique. |
| **PCA archetype discovery** | Strava has nothing like this. Visualizing workouts clustered by volume/intensity reveals training patterns invisible in a list view. |
| **Best segments over time** | Tracking PRs across standard distances with scatter + top-10 is a compelling "am I getting faster?" answer. |
| **Route-aware similarity** | Polyline haversine matching means "find workouts like this one" accounts for the actual course, not just similar numbers. This is technically non-trivial and a real moat. |
| **Fully local/private** | All analytics run on-device. No data leaves the machine except Strava OAuth. In a world of cloud-dependent fitness apps, this is a feature. |

### Value Leaks

These are the gaps where the product is losing user interest or failing to answer the questions athletes actually ask.

| Gap | Impact | Engineering Context |
|---|---|---|
| **No training load / fitness model** | The #1 question athletes ask is "am I overtraining or undertraining?" We have HR + pace + duration — the inputs for TSS/TRIMP/fitness-fatigue models — but don't compute them. | Requires new service. Inputs already exist in the `activities` table (pace, avg HR, duration). Could live alongside PCA/similarity in `DataService` analytics cache. |
| **No goals or targets** | The product is entirely backward-looking. No "I want to run a 3:30 marathon" -> "here's where you are." | New DB table for user goals, new dashboard widget, new comparison logic in activity detail. |
| **No weekly/monthly structure view** | Athletes think in training blocks (base, build, peak, taper). The calendar heatmap shows volume but not periodization. | `get_calendar_data()` already returns daily aggregates. A training block view would need block detection logic (volume/intensity change points) or manual user-defined blocks. |
| **Activity Detail is overloaded** | The detail page packs radar, splits, similar workouts, segments, map, timeline, and delta into one scroll. No clear hierarchy of "what should I learn from this workout?" | Refactor into tabbed layout. No new backend work — purely frontend restructure. |
| **Similarity Explorer feels disconnected** | PCA scatter is technically impressive but doesn't answer a clear user question. "Here are your clusters" — then what? | Needs contextual labels on clusters (e.g., "Easy runs", "Tempo efforts", "Long runs") and actionable takeaways. Could use cluster centroid analysis. |
| **No notifications or nudges** | After sync, users discover insights manually. No "you just set a 5K PR" or "your pace has declined 3 weeks running." | PR detection during sync (compare new segments against stored bests). Post-sync insight generation. |
| **Single-user, single-device** | SQLite + local venv means no multi-device sync, no sharing, no coaching. | Architectural constraint. Cloud-optional sync is Phase 3. |
| **No export or sharing** | Can't share a workout comparison, export a chart, or generate a training report. | Could start with static HTML/image generation. No backend changes needed for basic export. |

---

## 2. Strategic Roadmap

### Phase 1 — Value Validation (Weeks 1-4)

*Goal: Prove the product answers real athlete questions better than Strava's built-in analytics.*

#### P0: Post-Workout Insight Card

**What**: After sync, surface a single card on the dashboard and activity detail page summarizing what's notable about the latest workout(s).

**Examples of insights**:
- "New 5K PR: 22:14 (previous best: 22:31)"
- "Your pace has improved 15s/mi on this route over the last 3 months"
- "HR was 8bpm lower than similar-pace workouts — possible fitness gain"
- "This matches your 'tempo effort' archetype (Cluster 3)"

**Engineering notes**:
- New backend endpoint: `GET /api/activities/:id/insights` or compute during sync and store
- Inputs already available: similarity scores, best segments, trend data, PCA clusters
- Template-based generation first (no LLM needed). Pattern: compare latest activity against stored bests, rolling averages, and similar workouts
- Frontend: new `InsightCard` component, rendered at top of activity detail and as a dismissible banner on dashboard after sync

#### P0: Fitness & Fatigue Model (CTL/ATL/TSB)

**What**: Compute chronic training load (CTL, 42-day rolling avg), acute training load (ATL, 7-day rolling avg), and training stress balance (TSB = CTL - ATL) from existing data. Display as a single time-series chart on the dashboard.

**Why this is high-impact**: This is the metric every serious athlete wants. Strava locks it behind a $60/year subscription. We can compute it for free from data we already have.

**Engineering notes**:
- Training stress per workout = f(duration, HR, pace). Multiple models exist:
  - **TRIMP** (Training Impulse): duration * avg_HR_intensity_factor. Simplest, HR-only.
  - **hrTSS** (HR-based Training Stress Score): normalized to threshold HR. More accurate.
  - **rTSS** (Run TSS): pace-based, uses threshold pace. Best for runners without HR.
- Recommend starting with TRIMP — it only needs duration and avg HR, both of which we store for nearly every activity.
- New service: `backend/services/fitness_service.py`
- New endpoint: `GET /api/stats/fitness?date_from=&date_to=`
- Returns: array of `{ date, ctl, atl, tsb, daily_stress }` objects
- Cache at 2min TTL alongside trends data in `DataService`
- Frontend: new `FitnessChart` component on dashboard (Recharts area chart, 3 lines + shaded zones for "fresh", "optimal", "overreached")
- **User configuration needed**: threshold HR and/or threshold pace. Add to a settings endpoint or use auto-detection (median HR/pace from recent hard efforts).

#### P1: Activity Detail Redesign

**What**: Restructure the activity detail page into a tabbed layout to reduce cognitive overload.

**Proposed tab structure**:
1. **Overview** — map + key stats + insight card + progress timeline
2. **Splits** — pace/HR split charts + x-axis toggle
3. **Compare** — radar chart + similar workouts panel + performance delta
4. **Segments** — fastest segments table

**Engineering notes**:
- Purely frontend work. No backend changes.
- All data already fetched — just reorganize into tab containers
- Use URL hash or query param for tab state (`/activity/123?tab=splits`) so tabs are linkable
- Consider lazy-loading tab content to improve initial render

#### P1: Sync-Time PR Detection

**What**: During sync, compare new activity segments against stored personal bests. Flag new PRs and surface them prominently.

**Engineering notes**:
- In `SyncService`, after `add_activities()` and `compute_and_save_summaries()`, compare new summaries against existing bests per distance
- Store PR events in a new `pr_events` table: `activity_id, distance, time_seconds, previous_best_time, detected_at`
- New endpoint: `GET /api/activities/prs?since=<timestamp>` returns recent PRs
- Frontend: render PR badges on dashboard (after sync) and on activity detail header
- The `get_best_segments()` method in DataService already tracks bests — PR detection is a comparison during write, not a new query

---

### Phase 2 — Differentiators (Weeks 5-12)

*Goal: Build capabilities that competitors can't easily replicate.*

#### P0: Training Block Analysis

**What**: Let users define training blocks (or auto-detect them via volume/intensity change points) and compare block-over-block metrics.

**User story**: "In my build phase (Jan 15 - Mar 1), my threshold pace improved 12s/mi compared to base phase. Weekly volume increased 15% while avg HR stayed flat — good aerobic adaptation."

**Engineering notes**:
- **Auto-detection approach**: Use changepoint detection on weekly volume/intensity time series. The PCA infrastructure already computes volume vs intensity dimensions — apply a sliding window to detect phase transitions.
- **Manual approach**: New `training_blocks` table: `id, name, start_date, end_date, block_type (base/build/peak/taper/race)`. CRUD endpoints.
- New endpoint: `GET /api/stats/blocks` returns blocks with aggregate metrics (avg weekly volume, avg pace, avg HR, fitness trend within block)
- Frontend: new page or dashboard section. Timeline visualization showing blocks with key metrics per block and block-over-block deltas.
- **Start with manual blocks** — auto-detection is a nice-to-have that can be layered on.

#### P0: "Why Was This Workout Good/Bad?" Explainer

**What**: Generate a natural-language explanation for each workout using existing analytics.

**Example output**:
> This was your 3rd fastest 10K effort. Compared to similar workouts, your HR was 5bpm lower at the same pace, suggesting improved aerobic fitness. Your splits were evenly paced (negative split of 8s) — a sign of good race execution. This workout falls in your "threshold effort" archetype, which you've been doing more frequently in the last 6 weeks.

**Engineering notes**:
- Template-based first. Build a rule engine that combines:
  - Segment ranking (from `get_best_segments()`)
  - Similarity comparison (from `SimilarityService`)
  - Split analysis (even/negative/positive split detection from split data)
  - PCA cluster label (from `PCAService`)
  - Trend context (from `get_trend_data()` — is pace improving or declining?)
- New endpoint: `GET /api/activities/:id/explain`
- Returns structured explanation with sections: `{ headline, performance_context, comparison_context, pacing_analysis, trend_context }`
- Frontend: render as the insight card on the Overview tab of the redesigned activity detail
- **Future enhancement**: swap templates for local LLM summarization if desired, but templates are sufficient and faster

#### P1: Race Predictor

**What**: From best segments + recent fitness trend, estimate finish times for target distances.

**Engineering notes**:
- **Riegel formula**: `T2 = T1 * (D2/D1)^1.06` — predicts race time at distance D2 from a known time T1 at distance D1
- Use best recent segment (last 90 days) at closest available distance as T1
- Adjust for current form: weight by recent CTL trend (from fitness model)
- New endpoint: `GET /api/stats/predictions`
- Returns: `{ distance, predicted_time, confidence, based_on: { activity_id, segment_distance, segment_time, date } }`
- Predict for: 5K, 10K, half marathon, marathon
- Frontend: card grid on dashboard showing predicted times with "based on your 5K on March 12" attribution
- **Important caveat to display**: predictions are estimates, not guarantees. Show confidence range.

#### P1: Shareable Workout Reports

**What**: Generate a static image or HTML card summarizing a workout or comparison that can be shared externally.

**Engineering notes**:
- Server-side rendering approach: generate an HTML template, render to PNG via Puppeteer or a lightweight alternative
- Simpler approach: frontend-only using `html2canvas` or `dom-to-image` to capture the activity detail header + key chart as an image
- New frontend button: "Share" on activity detail page
- Include: activity name, date, key stats, mini map, and one chart (pace splits or radar)
- Branded with app logo/name for organic discovery
- **Start with frontend-only capture** — no backend work needed

---

### Source Agnosticism & Multi-Sport (Next Up)

*Goal: Make the app reflect the full picture of training — not just what Strava sees.*

**Context**: Apple Watch is the real source of truth. Strava captures runs, rides, and hikes because athletes manually share them. But strength training, functional fitness, and swimming often live only on the watch and in Apple Health. The app currently has a blind spot covering 2+ workouts per week.

The good news: the analytics layer (`DataService`, `PCAService`, `SimilarityService`) already reads from SQLite, not Strava. **Only `SyncService` and `strava_auth.py` know about Strava.** The data model is already mostly generic.

#### SA-1: Apple Health Import (P0)

**What**: Parse an Apple Health XML export and ingest all workouts into the existing SQLite schema.

**User flow**: Settings page → "Import Apple Health" → pick `export.xml` → progress bar → all Watch workouts appear in the activity feed.

**Engineering notes**:
- Apple Health exports via Health app → profile icon → "Export All Health Data" → produces `export.xml` (~100-500MB)
- Workout types in `HKWorkout` elements: `HKWorkoutActivityTypeRunning`, `HKWorkoutActivityTypeCycling`, `HKWorkoutActivityTypeSwimming`, `HKWorkoutActivityTypeTraditionalStrengthTraining`, `HKWorkoutActivityTypeFunctionalStrengthTraining`, `HKWorkoutActivityTypeHIIT`, `HKWorkoutActivityTypeYoga`, and ~80 others
- HR samples: `HKQuantityTypeIdentifierHeartRate` samples within the workout's time window
- GPS route: `HKSeriesType` route data with lat/lng/timestamp — present for outdoor activities, absent for indoor
- Distance: `HKQuantityTypeIdentifierDistanceWalkingRunning`, `HKQuantityTypeIdentifierDistanceSwimming`, etc.
- Swimming-specific: `HKQuantityTypeIdentifierSwimmingStrokeCount`, `HKQuantityTypeIdentifierLapLength`
- Deduplication: match against existing Strava activities by `(type, start_time)` within ±60 seconds; prefer Strava record (richer metadata) but backfill Apple HR/GPS if Strava record is HR-less
- New service: `backend/services/apple_health_service.py` — streaming XML parser (SAX, not DOM — files are too large for DOM)
- New endpoint: `POST /api/import/apple-health` — accepts multipart file upload
- New `source` column on `activities` table: `strava | apple_health | manual`
- Define `SyncProvider` interface in `backend/services/sync_provider.py` as part of this work; refactor Strava sync to implement it

**Key risk**: Apple Health XML is enormous. Use a streaming SAX parser, not `ElementTree.parse()`.

#### SA-2: Strength Training Support

**What**: Properly represent and track weight lifting and functional fitness sessions that have no GPS or pace data.

**Engineering notes**:
- New activity subtype: `strength` (covers `TraditionalStrengthTraining`, `FunctionalStrengthTraining`, `HIIT`)
- Schema already handles `null` for `pace`, `map_polyline`, `start_latlng` — no migrations needed
- CTL contribution: use duration + HR intensity (TRIMP). Most strength sessions will have HR from the watch. Falls back to duration-only estimate if no HR.
- Activity Detail view: strength activities should show a different tab layout — no Splits tab (no GPS splits), no Segments tab, no route map. Instead: duration, avg HR, estimated load, HR over time chart.
- Dashboard: strength workouts should count in the calendar heatmap (as a distinct color/pattern), and in weekly volume (by time, not miles)
- New activity type filter option in all lists/charts

#### SA-3: Swimming Analytics

**What**: Swim-specific metrics and a dedicated detail view for pool/open-water swims.

**Engineering notes**:
- Key swim metrics (from Apple Health):
  - **SWOLF** = stroke count per lap + seconds per lap (lower = more efficient)
  - **Pace per 100m/100yd** — the swimmer's equivalent of pace/mile
  - **Stroke count per lap** trend
  - **Total strokes**, **lap count**, **pool length** (25m/25yd/50m)
- New columns on `activities`: `pool_length_meters`, `stroke_count`, `swolf` (nullable, swim-only)
- Or store as a new `swim_laps` table (lap_number, time_seconds, stroke_count, swolf) — analogous to the `splits` table for runs
- Activity Detail swim view: pace/100 chart instead of pace/mile, SWOLF trend, lap breakdown table
- Similarity for swims: distance 40%, pace/100 30%, SWOLF efficiency 20%, HR 10%

---

### Phase 3 — Expansion (Months 4-12)

*Goal: Evolve from personal tool to platform.*

#### Multi-Source Ingestion (Beyond Apple Health)

**Context**: Once Apple Health is done, the `SyncProvider` interface is in place. Additional sources become incremental work.

**Implementation path**:
- Refactor `SyncService` to accept any `SyncProvider` (done as part of SA-1)
- Additional providers: Garmin Connect (API), Wahoo (API), Coros (API), Fitbit (API)
- Activity schema in DB is already generic (distance, pace, HR, elevation, polyline) — no schema changes needed for most sources
- **Biggest risk**: different sources have different data fidelity. Garmin has power/cadence/respiration. Apple Health has limited GPS. Need graceful degradation.

#### Coaching Mode

**What**: A coach sees multiple athletes' dashboards. Training load, compliance, and readiness across a roster.

**Implementation path**:
- Requires multi-user architecture: user accounts, athlete-coach relationships
- Move from SQLite to PostgreSQL (or keep SQLite per-user with a routing layer)
- New pages: coach dashboard (roster overview), athlete comparison
- **Monetization angle**: $10-20/month per coach seat, free for individual athletes
- **Prerequisite**: fitness model (Phase 1) and training blocks (Phase 2) must exist first

#### Cloud-Optional Sync

**What**: Keep local-first as default, add optional encrypted cloud sync for multi-device.

**Implementation path**:
- CRDTs or last-write-wins on the activity table (activities have Strava IDs as natural keys, so conflict resolution is straightforward)
- End-to-end encryption: encrypt SQLite DB before upload, decrypt on device
- Storage: S3-compatible object store
- **Privacy story**: "Your data is encrypted before it leaves your device. We can't read it. You can delete it anytime."

#### Plugin/Extension System

**What**: Let users add custom analytics modules.

**Examples**: power zone analysis (cyclists), elevation-adjusted pace (trail runners), swim metrics (triathletes), weight training volume tracking.

**Implementation path**:
- Define an analytics plugin interface: `input_features`, `compute(dataframe)`, `output_schema`
- Plugins register with `DataService` and get cached alongside PCA/similarity
- Frontend: plugin renders its own chart component via a standard props contract
- **Start by extracting PCA and similarity into this interface** as proof-of-concept plugins

---

## 3. High-Impact Opportunities

These are three features not covered in the roadmap above that could significantly move the needle.

### Opportunity A: Route Intelligence

**The insight**: We already decode and compare polylines via haversine matching in `SimilarityService`. This is an underused asset.

**The feature**: A "My Routes" page that clusters workouts by route (using existing haversine matching), then shows performance trends per route.

**What users see**:
- List of auto-detected routes (e.g., "River Loop — 4.2mi", "Hill Repeat Circuit — 3.1mi")
- Per-route: total times run, avg pace trend, best time, recent trend
- "On your river loop, your average pace has improved from 8:45 to 8:12 over 6 months. Your best time was Oct 15."
- Optional: pull historical weather data for GPS coordinates to show weather correlation

**Engineering notes**:
- Route clustering: group activities where route similarity > 85% (threshold tunable)
- Use the existing polyline comparison in `SimilarityService` but run it as a batch job to build a route graph
- New table: `routes` (id, name, representative_polyline, avg_distance)
- New join table: `route_activities` (route_id, activity_id, similarity_score)
- New endpoint: `GET /api/routes` and `GET /api/routes/:id/trends`
- Cache route clusters aggressively — they change only when new activities are synced
- Weather integration: OpenWeatherMap historical API (free tier: 1000 calls/day) using activity GPS centroid + date

**Why it wins**: Deeply personal data that no generic platform surfaces. Answers "am I getting faster on my regular routes?" — a universal runner question.

### Opportunity B: Morning Readiness Score

**The insight**: Athletes open their training app asking one question: "What should I do today?"

**The feature**: A daily readiness score (1-100) computed from training stress balance, recent workout density, and recovery patterns.

**What users see**:
- Single number on dashboard: "82 — Ready for intensity"
- Color-coded zones: Recovery (0-30), Easy (30-50), Moderate (50-70), Ready (70-85), Peak (85-100)
- Recommendation: "Recovery day", "Ready for tempo work", "Peak form — consider a race"
- 7-day readiness trend sparkline

**Engineering notes**:
- **Prerequisite**: Fitness model from Phase 1 (CTL/ATL/TSB)
- Readiness = f(TSB, days_since_last_hard_effort, weekly_volume_vs_target, recent_HR_drift)
- TSB is the primary input (positive TSB = fresh, negative = fatigued)
- Adjust for: consecutive rest days (recovery bonus), sudden volume spikes (overreach risk), HR drift in recent workouts (autonomic stress indicator)
- New endpoint: `GET /api/stats/readiness`
- Returns: `{ score, zone, recommendation, factors: { tsb, recovery_days, volume_trend, hr_drift } }`
- Frontend: prominent card at top of dashboard, above existing stat cards

**Why it wins**: Strava doesn't do this. Whoop charges $30/month for it (and requires a wearable). We can approximate it from existing data for free.

### Opportunity C: Training Narrative / Season Review

**The insight**: At the end of a training cycle or year, athletes want a story — not just charts. Strava's year-in-review is generic totals ("you ran 1,200 miles"). Ours could be meaningful.

**The feature**: A generated narrative that tells the story of a training period using all available analytics.

**What users see**:
- A scrollable visual report covering a selectable period (month, quarter, year, custom)
- Sections:
  - **Volume story**: weekly mileage trend with annotated peaks and valleys
  - **Fitness arc**: CTL/ATL/TSB chart with auto-detected phases labeled
  - **PR timeline**: all personal bests achieved in period, with context
  - **Route highlights**: most-run routes with per-route improvement
  - **Archetype evolution**: how PCA clusters shifted (e.g., "you moved from mostly easy runs to a mix of tempo and long runs")
  - **Key workouts**: top 5 workouts by training stress or PR significance
- Exportable as PDF or shareable HTML

**Engineering notes**:
- New endpoint: `GET /api/stats/narrative?from=&to=`
- Aggregates data from: `get_trend_data()`, `get_best_segments()`, PCA time-series, fitness model, route clusters
- Template engine generates structured sections (not free-form text)
- Frontend: dedicated page with scroll-triggered animations (intersection observer)
- PDF export: use browser print styling or a library like `jsPDF` + `html2canvas`
- **This is the "Spotify Wrapped" moment for athletes.** It creates emotional connection and organic sharing.

**Why it wins**: Requires exactly the analytics stack we've already built — PCA, similarity, segments, time-series, fitness model — just composed into a narrative. No competitor has the analytical depth to generate this.

---

## 4. Engineering Notes

### Architecture Principles Going Forward

1. **Keep analytics source-agnostic.** All analytics services read from SQLite, not from Strava. New features should follow this pattern. The sync layer is the only place that knows about external data sources.

2. **Cache at the right layer.** The existing TTL cache in `DataService` works well. New analytics (fitness model, readiness, insights) should plug into the same cache with appropriate TTLs. Fitness/readiness can use 2min TTL (same as trends). Insights can use 5min (same as PCA/similarity) since they're expensive to compute.

3. **Template before ML.** The insight card, workout explainer, and narrative features should all start as template/rule-based systems. They're faster, more predictable, and easier to debug. LLM-based generation can be layered on later as an enhancement.

4. **Frontend tab architecture for Activity Detail.** The redesign should use a lightweight tab system (not a library — just state + conditional rendering). Keep data fetching at the page level and pass to tabs as props. Lazy-load the Compare and Segments tabs since they require additional API calls.

5. **New tables needed** (in priority order):
   - `pr_events` — PR detection during sync (Phase 1)
   - `training_blocks` — manual block definitions (Phase 2)
   - `routes` + `route_activities` — route clustering (Opportunity A)
   - `user_settings` — threshold HR/pace for fitness model (Phase 1)

6. **New services needed** (in priority order):
   - `fitness_service.py` — CTL/ATL/TSB computation (Phase 1)
   - `insight_service.py` — post-workout insight generation (Phase 1)
   - `route_service.py` — route clustering and per-route trends (Opportunity A)

### Key Files Reference

| Area | File | What's There |
|---|---|---|
| API routes | `backend/api/activities.py` | All `/api/` routes: CRUD, sync, similarity, PCA, stats |
| Auth routes | `backend/api/auth.py` | Strava OAuth flow |
| Data access | `backend/services/data_service.py` | Singleton with SQLite reads + analytics cache |
| Similarity | `backend/services/similarity_service.py` | Weighted feature scoring + route matching |
| PCA | `backend/services/pca_service.py` | PCA + KMeans clustering |
| Sync | `backend/services/sync_service.py` | Background Strava sync thread |
| DB schema | `backend/services/database.py` | SQLite init + thread-local connections (WAL mode) |
| Schemas | `backend/models/schemas.py` | All Pydantic request/response models |
| Frontend API | `frontend/src/utils/api.js` | All fetch calls |
| State | `frontend/src/stores/appState.js` | React Context with caching |
| Router | `frontend/src/App.jsx` | Page routing |
| Dashboard | `frontend/src/pages/Dashboard.jsx` | Main dashboard page |
| Activity | `frontend/src/pages/ActivityDetail.jsx` | Workout detail page |
| Similarity | `frontend/src/pages/SimilarityExplorer.jsx` | PCA explorer page |

### New Files Added

| File | Purpose |
|---|---|
| `backend/services/fitness_service.py` | TRIMP computation, CTL/ATL/TSB EMA, readiness scoring |
| `frontend/src/components/FitnessChart.jsx` | Dual-axis ComposedChart: CTL/ATL lines + TSB dashed line + daily load bars |

### Schema Changes (additive, no migration needed)
- `user_settings` table — key/value store for `resting_hr`, future user preferences
- `pr_events` table — PR records detected after `sync_activity_details()` + `compute_and_save_summaries()`

### PR Detection Flow
1. User triggers "Fetch Details" on an activity → `sync_activity_details(activity_id)`
2. SyncService fetches Strava streams → builds 0.1mi splits → `DataService.add_splits()`
3. `add_splits()` → `compute_and_save_summaries()` → `detect_prs_for_activity()`
4. For each distance in the summaries, compare against all-time best from other activities of same type
5. If faster (or first effort), insert into `pr_events`
6. Dashboard PR banner queries `GET /api/activities/prs` on load

### Fitness Model Specifics
- **HR params**: max HR = 97th percentile of all recorded `max_heartrate` (auto-detected, no user input needed); resting HR = 60 bpm default (overridable via `user_settings` table)
- **TRIMP formula**: `duration_min × ΔHR × 0.64 × e^(1.92 × ΔHR)` where `ΔHR = (avg_HR - rest) / (max - rest)`
- **No-HR fallback**: pace-based intensity estimate (7 brackets from "very easy" to "hard")
- **CTL/ATL**: true EMA: `EMA[d] = EMA[d-1] + (stress[d] - EMA[d-1]) / window_days`
- **TSB**: computed as yesterday's CTL − yesterday's ATL (form entering today)
- **Accuracy note**: TRIMP slightly overestimates for high-HR short activities and underestimates for long easy efforts. Good enough for trend analysis; not a replacement for power-based TSS for cyclists.

### Competitive Moat

The defensible position is the combination of three things:

1. **Local-first privacy** — no data leaves the device, no subscription required for analytics
2. **Analytical depth** — PCA archetypes, route-aware similarity, split-level comparison across 5 workouts. No consumer fitness app offers this.
3. **Composability** — the analytics stack (PCA, similarity, segments, trends) can be composed into higher-order features (insights, narratives, readiness) that competitors would need to build from scratch

Protect all three. Every new feature should reinforce at least one.
