# Volken — Fable Roadmap

> **Vision**: Volken turns your Apple Health data into an interpretation layer for your body.
> Apple Health stores your data; Strava socializes your workouts; Bevel scores your recovery.
> Volken answers the questions in between: *Am I getting fitter? Was today's effort better than
> last time? What is my body telling me this morning, and does it actually show up in my
> performance?* — with no account, no cloud profile, and your data encrypted per-device.

_Last updated: 2026-07-10_

---

## 1. Where the product is today

An honest review of the current state, grounded in the code.

### What's strong

| Area | State |
|------|-------|
| **Workout ingestion** | Native HealthKit sync (`SyncEngine`, anchored + background delivery) with HR/GPS/distance streams; Apple Health XML upload for backfill. Source-agnostic activity model. |
| **Workout analytics** | Splits, rolling fastest segments, PR detection (`pr_events`), swim laps, strength overview, route matching + route pages, per-workout rule-based insights (`insight_service`). |
| **Training load** | TRIMP-based CTL/ATL/TSB (`fitness_service`), readiness banner, race predictor, training blocks. |
| **Exploration** | Similarity scoring (`similarity_service`), PCA/KMeans clustering, comparison of up to 5 activities. |
| **Privacy architecture** | Per-device SQLCipher DBs, wrapped DEKs, no accounts. This is a real, marketable differentiator — nobody else in this category can say "we couldn't read your data if we wanted to." |

### The honest gaps

1. **We are a workout app, not a health app.** The iOS sync uploads *only* `HKWorkout`
   objects (`SyncEngine.swift` → `HKWorkoutRequest`). Resting HR, HRV, sleep, VO₂max,
   respiratory rate, steps, weight — none of it is ingested. The DB has no table for
   daily metrics. The entire "how does my resting heart rate compare to a month ago"
   category **does not exist yet**.

2. **Readiness is half-blind.** `fitness_service` computes readiness purely from
   training load (TSB), with resting HR **hardcoded to a default of 60 bpm** unless the
   user manually sets it. Bevel/Whoop/Athlytic all fuse HRV + RHR + sleep. Ours can't
   until gap #1 is closed — but once it is, we have something they don't: the load
   model *and* the biometrics *and* the workout depth in one place.

3. **Post-workout comparison exists in pieces, not as a moment.** `InsightCard`,
   `SimilarWorkoutsPanel`, and `PerformanceDelta` are all on the ActivityDetail page,
   but the user has to scroll, manually pick comparisons, and synthesize the answer
   themselves. There is no single "you just finished — here's the verdict" experience,
   and nothing proactively tells you a new workout is ready to review.

4. **No cross-domain intelligence.** Nothing connects body metrics to performance
   ("you run faster after 8 hours of sleep"). Nobody in the market does this well —
   it's the wedge.

### Competitive position

| | Apple Health | Strava | Bevel / Athlytic | **Volken (target)** |
|---|---|---|---|---|
| Daily biometric trends | Raw charts, no interpretation | ✗ | ✓ (core product) | ✓ with rolling-average deltas + plain-language interpretation |
| Workout depth (splits, PRs, segments) | Minimal | ✓ (social-first) | Minimal | ✓ (already strong) |
| "How did this compare?" after a workout | ✗ | Segments/PRs only, GPS-social | ✗ | ✓ auto-matched by route & effort — **flagship moment** |
| Readiness | ✗ | Weak (Fitness/Freshness paywalled) | ✓ | ✓ fusing load **and** biometrics |
| Biometrics ↔ performance correlation | ✗ | ✗ | Weak | ✓ **unique** |
| Privacy | On-device | Cloud, social | Cloud | Encrypted per-device, no account |

**Thesis**: Bevel interprets your body. Strava interprets your workouts. Volken is the only
app that interprets both *and the relationship between them* — privately.

---

## 2. Roadmap

Sequencing logic: **Phase A** (biometrics pipeline) unlocks Phases C and D, so it starts
first even though **Phase B** (post-activity comparison) ships user value fastest — B has
zero dependency on A and should run in parallel. C and D are where differentiation
compounds. E is ongoing platform work.

---

### Phase A — Body Metrics Foundation (`BIO`) · P0

**Goal**: Ingest daily health metrics and answer "how does X compare to yesterday /
last week / last month / last year?" using rolling averages to suppress anomalies.

#### Epic A1: Ingestion pipeline

- [x] **BIO-1** — `health_metrics` table in per-device DB (`database.py` migration):
  `(date TEXT, metric TEXT, value REAL, min REAL, max REAL, source_id TEXT, UNIQUE(metric, date))`.
  One row per metric per day — daily granularity is enough for trends and keeps the
  table tiny (10 metrics × 365 days ≈ 3.6k rows/yr).
- [x] **BIO-2** — `POST /api/import/healthkit/metrics` (extend `import_routes.py`):
  batched upsert, same Bearer-token auth, flush DataService caches on write.
- [x] **BIO-3** — iOS: extend `SyncEngine`/`HealthKitManager` to sync daily metrics.
  Use `HKStatisticsCollectionQuery` (daily buckets) for: resting HR, HRV (SDNN),
  VO₂max, respiratory rate, step count, active energy, body mass, blood oxygen.
  Use `HKCategoryType` sleep analysis aggregated to nightly totals (asleep duration,
  time in bed; stage breakdown where available). Persist a per-metric "last synced
  date" (simpler and more robust than anchors for daily aggregates); re-fetch a
  trailing 7-day window each sync to pick up late-arriving Watch data.
- [x] **BIO-4** — Read new HK types in the Apple Health XML importer
  (`apple_health_service.py`) so web-side users get history backfill too. The XML
  export already contains `HKQuantityTypeIdentifierRestingHeartRate` etc. — we
  currently skip them.

#### Epic A2: Trends & comparison API

- [x] **BIO-5** — `GET /api/health/metrics/{metric}` in a new `backend/api/health.py`:
  returns daily series + **7-day and 30-day rolling means**, plus a comparison block:
  `{ today, vs_yesterday, vs_7d_avg, vs_30d_avg, vs_365d_avg, baseline_band }`.
  All deltas computed on rolling averages, not raw single days (the user's explicit
  requirement — one bad night shouldn't read as a trend). Baseline band = mean ± 1σ
  of the trailing 60 days, for "normal range" shading.
- [x] **BIO-6** — `GET /api/health/summary`: one call returning today's snapshot of all
  metrics with deltas, for the dashboard. Cache in the per-topic `_TTLCache` pattern.

#### Epic A3: Body dashboard

- [x] **BIO-7** — New "Body" section (own page in the bottom nav; Dashboard strip still todo): a tile per metric — big number, sparkline of the 30-day rolling mean,
  delta chip ("RHR 52 · **3 below** your 30-day avg"), colored only when outside the
  baseline band. Follow the existing DM Sans / dark palette system.
- [x] **BIO-8** — Metric detail view: raw dots + 7d/30d rolling lines + baseline band,
  range toggles (30D / 90D / 1Y / All) mirroring the Dashboard's existing time chips,
  and a plain-language interpretation line ("Your resting HR has drifted up 4 bpm over
  three weeks — this often tracks accumulated fatigue or illness").

---

### Phase B — The Post-Workout Moment (`CMP`) · P0, parallel with A

**Goal**: Within a minute of finishing an activity, Volken answers: *Was I faster?
Was it harder? Where does this rank?* — with zero taps of configuration.

#### Epic B1: Auto-comparison engine

- [x] **CMP-1** — `GET /api/activities/{id}/comparison` (new service,
  `comparison_service.py`, explicit `data_service=` injection per house rules).
  Selection cascade for the comparison cohort:
  1. **Same route** (route_activities match) — the gold standard: same course, true
     apples-to-apples;
  2. else **similar workouts** (reuse `similarity_service`, top-N above a score
     threshold, same type);
  3. else **same type + distance band** (±15%).
  Returns: cohort descriptor ("7 previous runs on this route"), rank (time and pace
  percentile), deltas vs cohort mean and vs personal best (pace, avg HR, HR drift),
  and a computed **efficiency verdict** — faster-at-lower-HR / faster-at-higher-HR /
  slower-but-easier etc. (2×2 of pace delta × HR delta).
- [x] **CMP-2** — **Relative Effort score**: expose per-activity TRIMP (already computed
  inside `fitness_service`) as a 0–100 percentile against the user's trailing 90 days.
  "Effort: 87 — your 3rd hardest session this quarter." This is the "is it harder
  effort for me" answer, and it works for strength/swim workouts with no pace.
- [x] **CMP-3** — Fold CMP-1/CMP-2 into `insight_service` headline generation so the
  one-sentence verdict is shared between the card, the push notification (CMP-5), and
  the weekly digest (COR-4).

#### Epic B2: The verdict UI

- [x] **CMP-4** — "How this compares" hero card at the **top** of ActivityDetail
  (above splits): verdict sentence, rank badge ("4th fastest of 12"), three delta
  stats (pace / HR / effort vs your average for this effort), sparkline of your
  history on this route/effort with this run highlighted. Reuses `PerformanceDelta`
  visual language; replaces manual comparison as the default path (manual multi-select
  stays for power users).
- [x] **CMP-5** — Post-sync local notification from the iOS app: background delivery
  already triggers sync (`registerWorkoutObserver`); after a successful upload of a
  new workout, fire "Your run is ready — 2nd fastest time on Riverside Loop 🎉" deep-
  linking to the activity. This makes Volken the app you open *right after* a workout
  instead of Strava.
- [x] **CMP-6** — Route detail page: add trend-over-attempts chart (time + HR per
  attempt) so "this route" history is a first-class page, not just a comparison input.

---

### Phase C — Readiness 2.0 (`RDY`) · P1, needs Phase A

**Goal**: Upgrade readiness from load-only to load + physiology — Bevel's core value,
plus the training context Bevel lacks.

- [x] **RDY-1** — Auto-derive resting HR from `health_metrics` (30-day rolling mean)
  instead of the hardcoded 60 bpm default in `fitness_service` — improves every TRIMP
  number retroactively. Keep the manual override in user_settings.
- [x] **RDY-2** — Readiness v2 score: blend TSB (existing) with same-morning deviations
  from baseline of HRV, RHR, and sleep duration. Rule-based and explainable — every
  score comes with "why": "TSB −8 (normal fatigue) · HRV 12% below baseline · 6.1h
  sleep → take it easy today." No black-box score; explainability is the brand.
- [x] **RDY-3** — Morning readiness push notification (opt-in) with the one-line "why".
- [x] **RDY-4** — Readiness history view: score over time overlaid on training load,
  with annotations where workouts contradicted the recommendation ("you went hard on
  a red day — HR was 7 bpm above normal for that pace").

---

### Phase D — The Correlation Engine (`COR`) · P1–P2, needs A + B

**Goal**: The moat. Connect what your body says to how you perform. No mainstream app
does this credibly.

- [x] **COR-1** — Effect analyses (start rule-based + simple stats, no ML): for each
  factor (sleep duration, HRV baseline deviation, RHR deviation, days since last hard
  effort), split the user's runs into cohorts and compare effort-adjusted pace.
  Surface only findings that clear a significance/sample-size bar: "Across 41 runs,
  you average **9s/mi faster** after nights with 7+ hours of sleep."
- [x] **COR-2** — **Efficiency trend**: pace-to-HR ratio (Efficiency Factor) per run,
  plotted as a rolling trend — the single best "am I actually getting fitter" chart,
  independent of how hard individual days felt. Add aerobic decoupling per long run
  (first-half vs second-half HR:pace from existing streams).
- [x] **COR-3** — Correlation cards on Dashboard, rotating, each dismissible and
  linkable to underlying data. Never show a claim the user can't inspect.
- [x] **COR-4** — Weekly digest (in-app first, notification later): synthesized
  narrative of the week — volume vs plan, efficiency trend, body-metric drift, best
  moment ("Tuesday's tempo was your 2nd best effort-adjusted run this year").

---

### Data quality (`DQ`) · done alongside Phases A–C

- [x] **DQ-1** — Retire the 0.1-mile split rollup (a workaround for old data
  limits we no longer have): new imports bucket at 0.05 mi with sub-second
  split times, and every consumer (fastest segments, summaries/PRs, insight
  split quality, split charts, comparison overlays) is now **grain-agnostic**
  — legacy 0.1-mi rows and new finer rows coexist with no migration. Fastest
  segments share one two-pointer implementation that scales windows to the
  exact target distance and can't be compressed by GPS dropouts; split-chart
  comparison overlays align by distance instead of array index. Re-run
  "full backfill" from Settings to rebuild old activities at the finer grain.

---

### Phase E — Platform & Polish (`PLT`) · ongoing

- [x] **PLT-1** — Lock-screen / home-screen **WidgetKit widgets**: readiness score +
  today's RHR/HRV deltas. Needs a small native data layer (widgets can't use the
  WKWebView) hitting `/api/health/summary` with the device token from the shared
  Keychain group. (VolkenWidgetsExtension: 4 widget families, shared keychain
  group, AfterFirstUnlock token accessibility, cached-snapshot offline fallback.)
- [ ] **PLT-2** — Unit preferences (mi/km, ft/m) in user_settings — currently
  imperial is hardcoded throughout `format.js`.
- [ ] **PLT-3** — Empty/loading states for the first-sync experience: new users see
  skeletons + "syncing 2 years of history" progress, not blank charts.
- [x] **PLT-4** — Data export additions: include `health_metrics` in the COMP-2 ZIP
  export and the COMP-1 purge. (Purge already covered — it removes the whole
  per-user dir; export now covers every table, with a schema-sync guard test.)
- [ ] **PLT-5** — Performance guardrail: `health_metrics` sync + rolling-average
  endpoints must stay <100ms warm; extend the `seeded_backend` fixture with seeded
  metrics so all of Phase A/C/D is testable per the conftest pattern.

---

## 3. What we deliberately are **not** building

- **Social features / leaderboards** — Strava owns this; competing there burns the
  privacy story that differentiates us.
- **Training plans / coaching subscriptions** — interpretation first; prescriptions
  are a later, riskier layer.
- **Android / non-Apple wearables** — the wedge is being the *best* Apple Health
  interpreter. Source-agnostic ingestion keeps the door open.
- **LLM-generated insights (for now)** — rule-based + statistics are explainable,
  free, offline, and private. Revisit only when a correlation is genuinely hard to
  narrate with templates.

## 4. Success metrics

- **Activation**: % of installs that complete first sync and view ≥1 comparison card.
- **The moment**: % of new workouts whose detail page is opened within 1 hour of sync
  (CMP-5 is the lever).
- **Retention driver**: DAU on days *without* a workout — only body metrics (Phase A)
  and readiness (Phase C) can create a daily habit; workouts alone cannot.
- **Differentiation proof**: % of weekly digests containing ≥1 correlation finding
  the user taps into.
