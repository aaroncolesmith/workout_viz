# Atlas — Go-to-Market Roadmap

> **The complete map of your training.**
> Working name: **Atlas** (trademark/App Store name clearance required before submission).
> Goal: ship to the App Store for real users, as fast as responsibly possible.

**Owner:** Aaron · **Drafted:** 2026-06-27 · **Status:** committed plan

---

## Committed Decisions

| Decision | Choice | Implication |
|---|---|---|
| **Architecture** | Hosted multi-tenant | Postgres, per-user data isolation, server-side compute. We become a health-data custodian — encryption + privacy policy + breach posture are now table stakes. The "local-first" marketing claim is retired. |
| **Monetization** | Free at launch | Ship 100% free to maximize adoption + feedback. Design the schema so a paywall (entitlements) can be retrofitted without migration. Eat hosting cost short-term. |
| **Name / brand** | Atlas | Maps + comprehensiveness; plays to route intelligence + multi-sport breadth. Tagline: "The complete map of your training." |
| **Primary data source** | Apple Health (HealthKit) | Strava shelved from the critical path (code kept dormant, not deleted). |
| **Default backfill** | Last 6 months | With a "Load 2 years" control. |

---

## Where We Are (honest baseline)

**Strong — done and differentiated:**
- Deep analytics: CTL/ATL/TSB fitness model, readiness, Riegel race predictor, PR detection, training blocks, PCA archetype clustering, route-aware similarity, best-segments, 5-workout split comparison.
- Multi-sport ingestion: Apple Health XML import + native iOS HealthKit sync engine (`ios/WorkoutViz/`) sending HR/GPS/distance streams + swim laps.
- Deployed (Railway/Fly) behind a SwiftUI WKWebView shell.

**The blockers between here and the store:**
1. **No concept of a user.** All HealthKit data flows through one shared `HEALTHKIT_API_KEY` into one global SQLite DB (`backend/api/import_routes.py:135`). No `user_id` exists. `DataService` is a process-wide singleton over a single `workouts.db`. *Cannot serve a second human as-is.*
2. **Auth is a Strava data connection, not a login** (`backend/api/auth.py`). No Sign in with Apple/Google.
3. **Data-fetching is a prototype**: hardcoded 365-day fetch, fire-and-forget, 30-min foreground throttle (`HealthKitManager.swift`). No background delivery, anchored incremental sync, resumability, or per-user dedup.
4. **Store mechanics missing**: no account deletion (required), no data export/delete (required for health data), no privacy nutrition label, no real icon/onboarding.

---

## Phase 1 — Identity & Multi-Tenancy  *(foundation; ~2–3 wks)*
*Nothing else ships until this lands. Auth, data, and branding all sit on top of it.*

- [ ] **Postgres migration.** Stand up Postgres; port schema from `database.py`. Add `users` table and `user_id` FK on `activities`, `splits`, `swim_laps`, `pr_events`, `routes`, `route_activities`, `training_blocks`, `user_settings`.
- [ ] **Sign in with Apple + Google.** Backend verifies the identity token → upserts user → issues a session JWT. (Apple Sign-In is mandatory once Google is offered.)
- [ ] **Scope every query to `user_id`.** `DataService` becomes per-user (or takes `user_id` on every call); retire the global singleton assumption. Replace shared-API-key ingest with JWT-authenticated, user-scoped ingest in `import_routes.py`.
- [ ] **iOS auth.** Native `ASAuthorizationController` (Apple) + Google SDK → exchange for session JWT → attach to all sync calls and inject into the WebView session.
- **Acceptance:** Two test accounts on two devices see only their own data, end to end.

## Phase 2 — Data-Fetching Service Rebuild  *(~1.5 wks)*
- [ ] **6-month default backfill** + **"Load 2 years"** control in onboarding and Settings.
- [ ] **Real incremental sync:** `HKAnchoredObjectQuery` + `HKObserverQuery` + **background delivery** so new Apple Watch workouts ingest without opening the app.
- [ ] **Idempotent, resumable, batched ingest** keyed on HK UUID *per user*; surfaced progress + error states.
- [ ] **Shelve Strava** from the critical path (keep dormant).
- **Acceptance:** New workout on the Watch appears in Atlas within minutes, unprompted; backfill is interruption-safe.

## Phase 3 — Branding & First-Run  *(~1 wk, parallel with P1/P2)*
- [ ] Finalize **Atlas** name (clearance), logo, app icon, splash.
- [ ] **Onboarding:** sign in → grant HealthKit → "mapping your last 6 months…" → first dashboard.
- [ ] Apply `design/DESIGN.md` premium pass so the WebView reads as native.

## Phase 4 — Launch Compliance & Submit  *(~1 wk)*
- [ ] **Account deletion** + **full data export/delete** (both required for health data).
- [ ] Privacy policy, `NSHealthShareUsageDescription`, App Privacy nutrition label, encryption-at-rest.
- [ ] TestFlight beta → fix → submit for review.

**Critical path to TestFlight: ~5–6 focused weeks, dominated by Phase 1.**

---

## Creative Features — Growth & Retention

Pull **#1 into launch scope**; fast-follow the rest.

1. **Shareable recap cards** *(launch)* — `html2canvas` → branded Atlas PNG. Every share = free distribution. Highest-ROI indie-launch feature.
2. **Season Review / "Training Wrapped"** *(fast-follow)* — composes existing analytics into a screenshot-worthy story.
3. **Goals & targets** *(fast-follow)* — "sub-3:30 marathon by Oct"; turns the product forward-looking, drives retention.
4. **Readiness-driven "what should I do today?"** surfaced on open.

---

## Deferred (post-launch, kept from prior roadmaps)
Strength/swim detail parity, similarity cluster labels, post-sync trend nudges, multi-source ingestion (Garmin/Wahoo/Coros), coaching mode, **and the paywall** (revisit once retention is proven — see Monetization decision).

---

## Top Risks
- **Health-data custodianship.** Hosted model makes us liable for everyone's HealthKit data. Encryption-at-rest, least-privilege access, and a real privacy policy are launch-blocking, not nice-to-have.
- **Name clearance.** "Atlas" is common; confirm App Store name + trademark availability early — have a fallback ready.
- **WebView rejection risk.** Defensible only because of native HealthKit value + native auth. Keep native surface area visible (onboarding, share sheet, auth) so it's not "just a website."
- **Phase 1 is the whole game.** Underestimating the SQLite→Postgres + per-user refactor is the most likely schedule slip.
