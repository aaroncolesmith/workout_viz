# 🔬 Similarity Engine — Deep Dive Roadmap

> **Problem Statement**: All similar workouts currently show **100% match**, even when the workouts are clearly different (e.g., a 5 mi @ 9:15/mi treadmill run vs a 7.04 mi @ 8:02/mi treadmill run). The similarity algorithm needs to produce meaningful, differentiated scores, and we want a rich visualization inspired by the NBA Aaronlytics "Archetype Clustering" PCA scatter plot.

---

## 📐 Root Cause Analysis

### Why Everything Shows 100%

The current algorithm in `backend/services/similarity_service.py` has two compounding issues:

1. **GPS Route Bonus Dominates** — Indoor/treadmill runs all have identical start/end GPS coords (e.g., your home gym). The bonus system gives **+0.2** for GPS start proximity *and* **+0.3** for waypoint matching — a **+0.5 boost** that pushes nearly every similar-type activity to 1.0.

2. **Feature Weights Under-weight Pace** — The weights are `[distance=0.6, elevation=0.2, pace=0.1, HR=0.1]`. Pace — the most discriminating feature for treadmill runs — only contributes 10% and the base score penalty from pace alone can only reduce the score by 0.1 at maximum.

3. **Bonus is Additive, Not Multiplicative** — Even when the base feature score is low (e.g., 0.7 for a very different workout), the GPS bonus pushes it past 1.0 and gets capped. The bonus should *amplify* similarity, not compensate for dissimilarity.

### Example Breakdown

| Workout | Distance | Pace | Elevation | HR |
|---------|----------|------|-----------|-----|
| **Target**: 5.03 mi @ 9:15/mi | 5.03 | 9.25 | 0 | 146 |
| **Similar A**: 5.01 mi @ 9:16/mi | 5.01 | 9.27 | 0 | 137 |
| **Dissimilar B**: 7.04 mi @ 8:02/mi | 7.04 | 8.03 | 0 | 155 |

After MinMaxScaler normalization (which only looks at the current batch), the weighted L1 distance between Target and Dissimilar B might be ~0.35, giving a base score of 0.65. But the +0.5 GPS bonus pushes it to 1.0 → `100% match`. **Wrong.**

---

## 🗺️ Phased Plan

### Phase S1: Fix the Scoring Algorithm (Backend)
> **Goal**: Make similarity scores meaningful and differentiated.

#### Epic S1.1: Redesign the Scoring Formula

**Current** (broken):
```
score = (1 - weighted_L1_distance) + gps_bonus
```

**Proposed** (new):
```
base_score = 1 - weighted_L1_distance(features)
route_factor = compute_route_similarity(gps)   # 0.0 to 1.0
final_score = base_score * (0.7 + 0.3 * route_factor)
```

Key changes:
- Route matching is a **multiplier**, not an additive bonus — it can only scale between 0.7x (no route match) and 1.0x (perfect route match), never inflate past the base score
- Rebalance feature weights to give pace proper influence
- Add **duration** as a feature (important for treadmill workouts where distance may vary slightly)

| Task | Description | Priority |
|------|-------------|----------|
| **S1.1.1** | Rebalance feature weights: `[distance=0.35, pace=0.30, HR=0.15, elevation=0.10, duration=0.10]` | ✅ Done |
| **S1.1.2** | Make GPS/route matching a **multiplicative factor** (0.7–1.0x) instead of additive bonus | ✅ Done |
| **S1.1.3** | Handle indoor/treadmill runs specially — when `trainer=True`, drop route factor entirely and redistribute weight to pace and duration | ✅ Done |
| **S1.1.4** | Use **population-level scaling** (pre-computed min/max per sport type across all activities) instead of per-query MinMaxScaler to ensure consistent scoring | ✅ Done |

> **S1.1.1–S1.1.3 are the critical bug fixes.** A 5mi @ 9:15 treadmill run vs a 7mi @ 8:02 treadmill run now shows ~62% similarity.

#### Epic S1.2: Enhanced Feature Engineering

| Task | Description | Priority |
|------|-------------|----------|
| **S1.2.1** | Add `moving_time_min` as a feature in the similarity vector | ✅ Done |
| **S1.2.2** | Add `average_cadence` as a low-weight feature (effort similarity signal) | 🟢 Low |
| **S1.2.3** | Compute pace *consistency* metric (std dev of split paces) | 🟢 Low |
| **S1.2.4** | Add time-of-day buckets as a categorical feature | 🟢 Low |

#### Epic S1.3: Similarity Score Transparency

| Task | Description | Priority |
|------|-------------|----------|
| **S1.3.1** | Return **component scores** alongside `similarity_score` | ✅ Done |
| **S1.3.2** | Return the **primary differentiating factor** | ✅ Done |
| **S1.3.3** | Add `similarity_tier` label: `"Near Identical" (>95%), "Very Similar" (80-95%)` | ✅ Done |


---

### Phase S2: Similarity Visualization — PCA Scatter Plot (Frontend)
> **Goal**: Port the NBA Aaronlytics "Archetype Clustering" PCA plot to workout data, enabling visual exploration of how workouts relate to each other in feature space.

#### Epic S2.1: Backend — PCA & Clustering Pipeline

| Task | Description | Priority |
|------|-------------|----------|
| **S2.1.1** | `GET /api/similarity/pca` — PCA endpoint | ✅ Done |
| **S2.1.2** | Add **DBSCAN or KMeans clustering** to auto-group activities | ✅ Done |
| **S2.1.3** | Compute **PCA loadings** — which features drive each principal component | ✅ Done |
| **S2.1.4** | Add `top_impact_stats` per activity | 🟢 Low |
| **S2.1.5** | Support **filtering by activity type** (Run, Ride, Hike) | ✅ Done |

#### Epic S2.2: Frontend — PCA Scatter Plot Component

Port the D3-based `PCAPlot.jsx` pattern from NBA Aaronlytics.

| Task | Description | Priority |
|------|-------------|----------|
| **S2.2.1** | Create `WorkoutPCA.jsx` — D3 scatter plot | ✅ Done |
| **S2.2.2** | Implement **PCA loadings overlay** | ✅ Done |
| **S2.2.3** | **Hover tooltips** with dynamic positioning and translucency | ✅ Done |
| **S2.2.4** | **Click interaction** for selection | ✅ Done |
| **S2.2.5** | **Zoom & pan** with state preservation | ✅ Done |
| **S2.2.6** | **Search** with highlight ring | ✅ Done |
| **S2.2.7** | **Toggle controls** for loadings/info | ✅ Done |

#### Epic S2.3: Similarity Explorer Page

| Task | Description | Priority |
|------|-------------|----------|
| **S2.3.1** | Create `/similarity` route and `SimilarityExplorer.jsx` page | ✅ Done |
| **S2.3.2** | **Tab layout** — Scatter Plot / Radar Profile | ✅ Done |
| **S2.3.3** | **Activity type filter bar** | ✅ Done |
| **S2.3.4** | **Cluster information** in sidebar | ✅ Done |
| **S2.3.5** | **"Pin" an activity** as selected target | ✅ Done |

---

### Phase S3: Enhanced Similar Workouts Panel (Frontend)
> **Goal**: Upgrade the existing "Similar Workouts" section on Activity Detail to show richer, more differentiated information.

#### Epic S3.1: Improve the Similar Workouts List

| Task | Description | Priority |
|------|-------------|----------|
| **S3.1.1** | **Color-coded match badges** — tiers: High, Medium, Low | ✅ Done |
| **S3.1.2** | **Show component breakdown inline** — display match % per feature | ✅ Done |
| **S3.1.3** | **Show key difference** — highlight the most deviating stat | ✅ Done |
| **S3.1.4** | **Similarity tier labels** — mapped to badge colors | ✅ Done |

#### Epic S3.2: Mini PCA Plot on Activity Detail

| Task | Description | Priority |
|------|-------------|----------|
| **S3.2.1** | Embed a **small PCA scatter plot** on the Activity Detail page | ✅ Done |
| **S3.2.2** | Connect the mini PCA to the similar list | 🟢 Low |

---

## 🔀 Cross-Reference with Main ROADMAP.md

The following tasks from the main ROADMAP overlap with or are superseded by this plan:

| ROADMAP Task | Status | Relation to This Plan |
|-------------|--------|----------------------|
| **Task 3.1.1**: Implement similarity vector builder (cosine similarity) | ✅ Done | **Superseded by S1.1.1–S1.1.4** — rebalancing weights and switching to multiplicative route scoring |
| **Task 3.1.2**: GPS proximity scoring (haversine) | ✅ Done | **Refined by S1.1.2** — making it multiplicative instead of additive |
| **Task 3.1.2b**: Route waypoint matching | ✅ Done | **Refined by S1.1.2** — same waypoint logic, different scoring model |
| **Task 3.1.3**: Pre-compute similarity matrix per type | ❌ Open | **Addressed by S1.1.4** — population-level scaling is a prerequisite; full matrix pre-computation deferred |
| **Task 3.1.4**: DBSCAN/hierarchical clustering | ❌ Open | **Now S2.1.2** — folded into the PCA pipeline |
| **Task 3.2.2**: `GET /api/clusters` | ❌ Open | **Now S2.1.1** — combined with PCA endpoint |
| **Task 3.2.3**: `GET /api/clusters/{id}/trend` | ❌ Open | **Deferred** — not in initial similarity scope |
| **Task 3.3.1**: Route cluster cards | ❌ Open | **Now S2.3.4** — cluster cards on the Similarity Explorer page |
| **Task 3.3.3**: Cluster naming | ❌ Open | **Deferred** — auto-generated labels first (e.g., "5mi Easy Runs") |

> Once Phase S1 is complete, we should update the main ROADMAP to mark Tasks 3.1.1–3.1.2b as "revised" and link to this document for the updated spec.

---

## 📋 Implementation Priority Order

| Priority | Phase | Tasks | Effort | Impact |
|----------|-------|-------|--------|--------|
| 🔴 **P0** | S1.1 | S1.1.1–S1.1.3 — Fix scoring formula | **Low** (1 file, ~50 lines) | **Critical** — fixes the 100% bug |
| 🔴 **P1** | S3.1 | S3.1.1 — Color-coded badges | **Low** (CSS + JSX) | **High** — instant visual improvement |
| 🟡 **P2** | S1.3 | S1.3.1–S1.3.3 — Score transparency | **Medium** | **High** — shows users *why* |
| 🟡 **P2** | S3.1 | S3.1.2–S3.1.3 — Component breakdown | **Medium** | **High** — detail on hover |
| 🟡 **P3** | S2.1 | S2.1.1–S2.1.3 — PCA backend | **Medium** | **High** — unlocks viz |
| 🟡 **P3** | S2.2 | S2.2.1–S2.2.3 — PCA scatter plot | **High** | **High** — wow factor |
| 🟡 **P4** | S2.3 | S2.3.1–S2.3.5 — Explorer page | **High** | **Medium** — full experience |
| 🟢 **P5** | S1.2 | S1.2.1–S1.2.4 — Enhanced features | **Low** | **Low** — refinement |
| 🟢 **P5** | S3.2 | S3.2.1–S3.2.2 — Mini PCA on detail | **Medium** | **Low** — polish |

---

## 🎯 Success Criteria

When this work is complete, the following should be true:

1. **5 mi @ 9:15/mi treadmill runs** show **>95% match** to each other
2. **7.04 mi @ 8:02/mi treadmill run** shows **~55-65% match** to the 5-milers (same type, different effort profile)
3. **Outdoor runs on the same route** get a route similarity boost over different-route runs
4. The **Similarity Explorer** page provides an interactive PCA scatter plot where you can visually see clusters of similar workouts
5. The **Similar Workouts** panel uses color-coded badges and shows *why* workouts are similar or different

---

## 🔧 Technical Notes

### Dependencies
- **D3.js** — already used in NBA aaronlytics for PCA plot; needs to be added to workout_viz frontend
- **scikit-learn** — already in backend requirements; PCA + DBSCAN from sklearn
- **No new backend dependencies** — similarity fixes are pure logic changes

### Key Files to Modify/Create

| File | Action | Phase |
|------|--------|-------|
| `backend/services/similarity_service.py` | **Modify** — rewrite scoring formula | S1 |
| `backend/api/activities.py` | **Modify** — add PCA endpoint | S2 |
| `backend/services/pca_service.py` | **Create** — PCA + clustering pipeline | S2 |
| `frontend/src/components/WorkoutPCA.jsx` | **Create** — D3 scatter plot component | S2 |
| `frontend/src/pages/SimilarityExplorer.jsx` | **Create** — new page | S2 |
| `frontend/src/pages/ActivityDetail.jsx` | **Modify** — enhanced similar panel | S3 |
| `frontend/src/index.css` | **Modify** — color-coded badge styles | S3 |
