# Launch Roadmap Docs — Engineering Handoff

This directory is the complete handoff for taking the app from a **single-user analytics tool** to a **multi-user App Store product**. Start here, then read the three docs in order.

> **Working app name: TBD** (Aaron is finalizing — "Atlas" was a placeholder, likely taken). Code uses an `APP_NAME` constant so the rename is one line.

---

## TL;DR — what we're building

The analytics engine (fitness model, race predictor, PCA archetypes, route intelligence, 5-workout comparison) is **already built and strong**. The gap to launch is **not features** — it's that the product has **no concept of a user**: all HealthKit data currently flows through one shared API key into one global SQLite DB. The work here makes it multi-tenant, authenticated, encrypted, and App-Store-compliant.

### Confirmed decisions (don't relitigate)
| Area | Decision |
|---|---|
| Tenancy | Hosted, multi-tenant |
| Data isolation | **SQLite-per-user** (one encrypted DB file per user) — *not* Postgres; chosen to avoid a multi-week SQL dialect port |
| Auth | Sign in with **Apple + Google** → backend-issued session JWT |
| Encryption | **SQLCipher** on every per-user DB + the identity DB (in scope for launch) |
| Key model | Wrapped per-user DEKs behind a `KeyProvider` seam; master in platform secrets at launch, KMS fast-follow |
| Data source | **Apple Health / HealthKit** (Strava shelved, code kept dormant) |
| Backfill | Last **6 months** default, "Load 2 years" action |
| Monetization | **Free at launch** (schema designed so a paywall can be added later) |

---

## Read in this order

1. **`LAUNCH_ROADMAP.md`** — *the why & what.* Product state, the 4 launch phases, growth features, risks. ~10 min. Read first for context.
2. **`ENGINEERING_SPEC.md`** — *the how.* Target architecture, per-workstream technical detail (A–E), data model, API contracts, SQLCipher key model, and **Appendix C** (master-key custody & rotation). The reference doc you'll keep open while building.
3. **`TICKETS.md`** — *the do.* ~32 tickets across 8 epics, each with acceptance criteria, dependencies, estimates, and labels. Copy straight into Linear/GitHub.

---

## Where to start coding

Critical path is **AUTH → DATA → IOS → HK**. In ticket order:

1. **`SEC-1`** (today) — rotate the leaked `HEALTHKIT_API_KEY` (it's committed in `ios/WorkoutViz/Config.swift:9`).
2. **`SEC-2`** — provision launch secrets.
3. **`AUTH-1…5`** — identity DB, Apple/Google verification, session JWT, login endpoints, `get_current_user`.
4. **`DATA-1…7`** — encrypted per-user data layer + `DataService(user_id)` registry + legacy-DB adoption.
5. **`IOS-1…3`**, then **`HK-1…4`**, with **`BRAND-*`** in parallel and **`COMP-*`** before submission.

Do **not** parallelize AUTH/DATA away — everything else depends on them. Full sequencing table is at the top of `TICKETS.md`.

---

## Codebase orientation (current state)

- **Backend** — FastAPI + SQLite, venv at `./venv/`. Entry `backend/main.py`; routes in `backend/api/`; the singleton + analytics in `backend/services/data_service.py`; schema + connections in `backend/services/database.py`. See root `CLAUDE.md` for the full map.
- **Frontend** — React 19 + Vite in `frontend/`. All API calls in `frontend/src/utils/api.js`.
- **iOS** — SwiftUI WKWebView shell + HealthKit sync engine in `ios/WorkoutViz/`. Setup in `ios/SETUP.md`.
- **Tests** — `backend/tests/`; `seeded_backend` fixture in `conftest.py` (must become per-user — see `QA-1`).

---

## Open decisions (need Aaron, don't block starting)

1. **Final app name** — gates the App Store listing + `APP_NAME` constant. Not code-blocking.
2. **Master-key custody** — env-now vs KMS-now. Recommendation: env-now behind the `KeyProvider` seam, KMS as `COMP-5` fast-follow (see Appendix C). Confirm the **master-key escrow/backup** location regardless — losing it loses all user data.

## Top risks
- **Health-data custodianship** — the hosted model makes us liable for everyone's HealthKit data. Encryption (SQLCipher) + privacy policy + account deletion are launch-blocking, not optional.
- **Phase 1 (AUTH+DATA) is the whole game** — underestimating the multi-tenant refactor is the most likely slip.
- **WebView rejection risk** — defensible only because of native HealthKit + native auth value. Keep native surface area (onboarding, sign-in, share sheet) visible.

---

*Estimate: ~38 dev-days ≈ 5–6 calendar weeks for one engineer to TestFlight.*
