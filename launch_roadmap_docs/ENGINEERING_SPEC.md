# Engineering Spec — Multi-Tenant Launch

> Working app name: **TBD** (Aaron is finalizing; "Atlas" was the placeholder but is likely taken). Use `APP_NAME` constants/env everywhere so the rename is a one-line change.
>
> **Goal:** take the existing single-user analytics tool to a multi-user App Store app. Hosted multi-tenant, free at launch, Apple Health as the data source.
>
> **Companion docs:** `LAUNCH_ROADMAP.md` (product/sequencing). This doc is the engineering detail for handoff.

---

## 0. Confirmed architecture decisions

| Decision | Choice |
|---|---|
| Tenancy | Hosted, multi-tenant |
| Data isolation | **SQLite-per-user** — one `workouts.db` file per user on a persistent volume. No SQL dialect port; analytics code unchanged. |
| Identity | Sign in with Apple **and** Google → backend-issued session JWT |
| Data source | Apple Health / HealthKit (Strava shelved, code dormant) |
| Default backfill | Last **6 months**, with a "Load 2 years" action |
| Monetization | Free at launch (design schema so entitlements can be added later) |

---

## ⚠️ 0.1 Fix first — leaked secret

`ios/WorkoutViz/Config.swift:9` hardcodes a real `HEALTHKIT_API_KEY` and it's committed to git.
- **Rotate** the key on the server now (it's in history).
- The shared-key auth model is being removed entirely (Workstream C3), but until then: rotate, and scrub from history if the repo will ever be public.

---

## 1. Target architecture

```
┌─────────────────────────── iOS app ───────────────────────────┐
│  Sign in with Apple / Google  →  session JWT (Keychain)        │
│  HealthKitManager (anchored + background delivery)             │
│  SyncEngine  ──Bearer JWT──┐                                   │
│  WKWebView (React app, JWT injected) ──Bearer JWT──┐           │
└────────────────────────────┼──────────────────────┼───────────┘
                             ▼                      ▼
                    ┌──────────────── FastAPI ────────────────┐
                    │ auth middleware: verify JWT → user_id    │
                    │ get_current_user dependency on every route│
                    └───────────────┬──────────────────────────┘
                                    ▼
              ┌─────────────────────────────────────────┐
              │ DataServiceRegistry  get_data_service(uid)│
              │   → DataService bound to that user's DB   │
              └───────────────┬───────────────────────────┘
        ┌───────────────────┐ │ ┌─────────────────────────────┐
        │ /data/users.db     │ │ │ /data/users/<uid>/workouts.db│  (one per user)
        │ (identity registry)│   │ /data/users/<uid>/.anchor    │
        └────────────────────┘   └──────────────────────────────┘
```

Two database tiers:
1. **Central registry** `users.db` — identity, provider links, sessions. Small, shared.
2. **Per-user** `users/<uid>/workouts.db` — the *existing* schema verbatim. Created on first login from the current `_create_schema()`.

---

## 2. Workstream A — Identity & Auth

### A1. Central registry DB (`backend/services/identity_db.py`, new)

New SQLite file at `DATA_DIR/users.db`, its own `init_identity_db()` + `get_identity_conn()` (mirror `database.py` thread-local pattern).

```sql
CREATE TABLE users (
    id            TEXT PRIMARY KEY,         -- uuid4 hex; also the per-user DB folder name
    email         TEXT,                     -- may be null/relay (Apple private relay)
    display_name  TEXT,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT,
    deleted_at    TEXT                       -- soft-delete tombstone; hard delete purges file
);

CREATE TABLE identities (
    provider      TEXT NOT NULL,            -- 'apple' | 'google'
    provider_sub  TEXT NOT NULL,            -- stable subject id from the provider
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email         TEXT,
    PRIMARY KEY (provider, provider_sub)
);

CREATE TABLE sessions (                      -- optional: enables server-side revocation
    jti           TEXT PRIMARY KEY,          -- token id
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issued_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at    TEXT,
    revoked       INTEGER DEFAULT 0
);
```

### A2. Provider token verification (`backend/services/auth_providers.py`, new)

Both providers send the client a signed OIDC **ID token** (JWT). Backend verifies it — never trust client-sent user ids.

**Apple** (`POST /api/auth/apple`, body `{ identity_token, full_name? }`):
- Fetch & cache Apple's JWKS from `https://appleid.apple.com/auth/keys`.
- Verify signature (RS256), `iss == https://appleid.apple.com`, `aud == <iOS bundle id>`, `exp` not passed.
- Subject = `sub`. Email = `email` claim if present (first login only; may be a private-relay address).

**Google** (`POST /api/auth/google`, body `{ id_token }`):
- Verify against `https://www.googleapis.com/oauth2/v3/certs`, `iss in {accounts.google.com, https://accounts.google.com}`, `aud == <Google OAuth client id>`, `exp`.
- Subject = `sub`, email = `email`.

Use `python-jose[cryptography]` or `pyjwt[crypto]` + a small JWKS cache. Add deps to `requirements`.

### A3. Login → user resolution → session JWT

Shared logic after either provider verifies:
1. Look up `identities(provider, provider_sub)`.
2. If found → that `user_id`. If not → create `users` row (uuid4), insert identity, **create the per-user DB** (`init_db` against `users/<uid>/workouts.db`).
3. Update `last_login_at`, issue session JWT.

**Session JWT** (`backend/services/session.py`, new):
- HS256, signed with `SESSION_JWT_SECRET` (new required env var, 32+ bytes random).
- Claims: `sub=user_id`, `jti=uuid4`, `iat`, `exp` (30 days). Insert `jti` into `sessions`.
- Response: `{ access_token, expires_at, user: { id, email, display_name } }`.
- **Refresh:** `POST /api/auth/refresh` (valid token within 7 days of expiry → new token). Simpler than refresh tokens for launch.

### A4. Auth dependency (replaces Strava-centric `auth.py`)

```python
# backend/api/deps.py  (new)
async def get_current_user(authorization: str = Header(None)) -> str:
    # parse "Bearer <jwt>", verify sig+exp, check jti not revoked → return user_id
    # raise 401 otherwise
```

- Apply to **every** data route (see B5).
- `backend/api/auth.py`: replace Strava endpoints with `/api/auth/apple`, `/api/auth/google`, `/api/auth/refresh`, `/api/auth/me`. Keep Strava routes only behind a dormant feature flag.

### A5. iOS auth

- **Apple:** `AuthenticationServices` → `ASAuthorizationAppleIDProvider` → on success POST `identityToken` to `/api/auth/apple`.
- **Google:** `GoogleSignIn` SDK → POST `idToken` to `/api/auth/google`.
- Store returned session JWT in **Keychain** (not UserDefaults).
- Attach `Authorization: Bearer <jwt>` to all `SyncEngine` requests (replaces `X-Api-Key`).
- **WebView session:** before loading the React app, inject the token so `api.js` can use it:
  ```swift
  let script = WKUserScript(source: "window.localStorage.setItem('session_token', '\(jwt)')",
                            injectionTime: .atDocumentStart, forMainFrameOnly: true)
  ```
  Update `frontend/src/utils/api.js` to read `localStorage.session_token` and send it as `Authorization`. Add a 401 handler that signals the native shell to re-auth.
- Onboarding gate: no token → show native sign-in screen; don't load the WebView until authed.

**Acceptance (A):** Two accounts on two devices each sign in, get distinct `user_id`s, and every API response contains only their own data. Killing/reinstalling preserves login via Keychain.

---

## 3. Workstream B — Multi-tenant data layer (SQLite-per-user)

The analytics SQL does **not** change. Only connection routing and the singleton change.

### B1. Connection routing (`backend/services/database.py`)

Replace the single global `_DB_PATH` + single thread-local `conn` with a **path-keyed** thread-local map:

```python
_local = threading.local()   # _local.conns: Dict[str, sqlite3.Connection]

def get_conn(db_path: str) -> sqlite3.Connection:
    conns = getattr(_local, "conns", None) or {}
    conn = conns.get(db_path)
    if conn is None:
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        # ...same PRAGMAs as today...
        conns[db_path] = conn; _local.conns = conns
    return conn

def init_db(db_path: str):   # unchanged body, but path is now a param, not global
    _create_schema(db_path); _migrate_schema(get_conn(db_path))
```

All the `_create_schema` / `_migrate_*` functions take an explicit `conn` (most already do). `get_best_segments`, etc., are untouched — they call through `DataService`.

> **Note:** thread-local × path means connections = threads × active users. Fine at launch scale. Add an idle-eviction cap (B3) before it matters.

### B2. DataService becomes per-user

Today `DataService.__init__` hardcodes `DB_PATH` and every method calls module-level `get_conn()`. Change:
- `DataService.__init__(self, user_id: str)` sets `self.user_id`, `self.db_path = DATA_DIR/"users"/user_id/"workouts.db"`, calls `init_db(self.db_path)`, owns its **own** `_TTLCache`.
- Mechanical replace inside `data_service.py`: `get_conn()` → `get_conn(self.db_path)`. (~40 call sites — all already inside `DataService` methods per the grep.) The handful of static helpers that don't touch the DB are unaffected.

### B3. Registry / lifecycle (`get_data_service`)

Replace the module singleton with a small registry:

```python
class DataServiceRegistry:
    # LRU dict user_id -> (DataService, last_used); lock-guarded.
    # Cap N (e.g. 200) active; on eviction close that user's connections.
    def get(self, user_id: str) -> DataService: ...

def get_data_service(user_id: str) -> DataService:
    return _registry.get(user_id)
```
- On eviction, close the evicted user's thread-local connections (add `close_conns(db_path)` to `database.py`).
- Startup (`main.py`) no longer warms a global service. It only `init_identity_db()`. Per-user DBs are created lazily at first login. Remove/relocate the `_backfill_extended_pr_distances` background job — it must run **per user** on first access, not globally (move the trigger into `DataService.__init__`, gated by that user's `user_settings` flag — the existing flag logic already lives in `user_settings`, which is now per-user, so it Just Works).

### B4. Adopt the existing single-user database

Aaron's current global `workouts.db` has real history. On his first login:
- Add env `ADMIN_ADOPT_EMAIL`. When a login's verified email matches and `users/<uid>/workouts.db` doesn't exist yet but a legacy `DATA_DIR/workouts.db` does → **move** the legacy file into `users/<uid>/workouts.db` before first use. One-shot, logged.
- Provide `backend/scripts/adopt_legacy_db.py` to do this manually too.

### B5. Endpoint scoping (`backend/api/*`)

Every route in `activities.py`, `routes.py`, `import_routes.py` gains `user_id: str = Depends(get_current_user)` and uses `get_data_service(user_id)`.
- Audit for any route still calling `get_data_service()` with no arg → must fail typecheck/CI.
- `auth.py` `/status` etc. become user-scoped or are removed.
- Remove the global cache endpoints in `main.py` (`/api/cache/*`) or scope them to the current user.

### B6. Encryption at rest — SQLCipher (in scope for launch)

Per-user DBs are encrypted on disk with **SQLCipher**. Server-side only — no health data is stored on the device, so iOS needs no SQLCipher (the Keychain JWT is the only device secret).

- **Library:** `sqlcipher3-binary` (ships SQLCipher in the wheel — no system `libsqlcipher` needed; verify the Docker base image builds it, add build deps if not). `get_conn` (B1) swaps `sqlite3.connect` → `sqlcipher3.dbapi2.connect`.
- **Per-user key model:** **wrapped DEKs** (recommended over plain HKDF — see Appendix C for why). Each user gets a random 32-byte Data Encryption Key (DEK); the DEK is stored **wrapped** (AES-GCM with the master) in their `identities`/`users` row. At connect: load wrapped DEK → unwrap with master in memory → `PRAGMA key` with the DEK. This makes master rotation O(number of users), not O(total data). (A plain `HKDF(master, salt=user_id)` derivation is the simpler fallback if you accept expensive rotation.) All key handling goes through the `KeyProvider` seam (Appendix C) so master custody is swappable.
- **Applying the key:** immediately after `connect()`, before any other statement: `conn.execute("PRAGMA key = \"x'<hex_key>'\"")` then `conn.execute("PRAGMA cipher_compatibility = 4")`. Then the existing PRAGMAs (WAL, foreign_keys, etc.). Wrong/missing key → first query raises `NotADatabase`; surface as 500, never auto-recreate.
- **Identity DB:** encrypt `users.db` too, keyed directly from the master (salt = `"identity"`).
- **Key rotation:** document `PRAGMA rekey` per file; provide `backend/scripts/rekey_dbs.py` (iterate users, old key → new key). Not automated for launch, but the script must exist.

### B4 ⟶ adoption now encrypts

The legacy `workouts.db` is **plaintext**. Adoption must encrypt-on-import, not just move the file:
- Open legacy plaintext DB, `ATTACH DATABASE 'users/<uid>/workouts.db' AS enc KEY "x'<userkey>'"`, run `SELECT sqlcipher_export('enc')`, `DETACH`. Then delete the plaintext original.

**Acceptance (B):** With two seeded user DBs, `GET /api/activities` returns disjoint sets per token; deleting one user's file leaves the other intact; first login adopts + **encrypts** the legacy DB exactly once; opening any per-user `.db` file with plain `sqlite3` fails (confirms encryption).

---

## 4. Workstream C — Data-fetching service rebuild (HealthKit)

### C1. Backfill window
- `Config.initialSyncDays`: `365 → 182` (6 months) as the default first sync.
- Add a Settings/onboarding action **"Load 2 years"** → triggers `performSync(force: true, since: 2 years ago)`. Keep the resumable chunked backfill in `SyncEngine` (already solid).
- Drop the 10-year `performFullBackfill` from the default UI (keep as a hidden/debug action).

### C2. Incremental + background sync (the real upgrade)
Replace "fetch last N days on foreground, throttle 30 min" with anchored + observed delivery:
- **`HKAnchoredObjectQuery`** over `workoutType()` with a persisted `HKQueryAnchor` (store in UserDefaults/Keychain, **per logged-in user**). Returns only new/changed/deleted workouts since the anchor — replaces the manual `since`-date + UUID-diff logic as the primary path (keep UUID set as a dedupe backstop).
- **`HKObserverQuery`** + `enableBackgroundDelivery(for: .workoutType(), frequency: .immediate)` so new Apple Watch workouts wake the app and sync without manual open.
- Entitlement: add `com.apple.developer.healthkit.background-delivery` to `WorkoutViz.entitlements`; enable **Background Modes** (background fetch/processing). Handle deletions (anchored query returns `deletedObjects`) → `DELETE` on backend.
- On logout/account-switch: reset the anchor and synced-id set so a new user doesn't inherit the previous anchor.

### C3. Authenticated, user-scoped ingest
- `POST /api/import/healthkit` and `/healthkit/missing-streams`: drop `X-Api-Key` / `_require_healthkit_key`; use `get_current_user`. Write to `get_data_service(user_id)`.
- The negative-hash `_hk_id` ID scheme stays (per-user DB, so collisions across users are irrelevant). Dedupe logic in `import_routes.py` is unchanged but now operates within one user's DB.
- `HEALTHKIT_API_KEY` env + `_require_healthkit_key` deleted after migration.

### C4. Sync status
- Keep `SyncEngine`'s `@Published` progress for the native shell.
- Optional: surface "last synced" + counts from the backend (per-user `sync_log`).

**Acceptance (C):** New workout recorded on the Watch appears in the app within minutes with the app backgrounded; first-run pulls 6 months; "Load 2 years" extends history; all ingest is attributed to the authenticated user only.

---

## 5. Workstream D — Branding & first-run

- `APP_NAME` constant in frontend + iOS display name + a single backend `app` string (`main.py:97`) — wire to env/constant so the final name is a one-line change.
- Assets: app icon, launch screen, logo in the WebView header, share-card branding.
- Onboarding flow (native): **Sign in → grant HealthKit → "Importing your last 6 months…" progress → Dashboard.** Don't load the WebView until authed + first sync kicked off.
- Apply `design/DESIGN.md` premium pass (typography, monochrome surfaces) so the WebView reads as native.

## 6. Workstream E — Launch compliance (App Store gating)

- **Account deletion (required):** `DELETE /api/account` → purge `users/<uid>/` dir, registry rows, sessions; native "Delete account" in Settings that calls it and signs out. Must fully delete, in-app.
- **Data export:** `GET /api/account/export` → zip the user's `workouts.db` (+ a JSON manifest). Trivial with per-user files.
- **Sign in with Apple:** mandatory because Google login is offered — already in scope (A5).
- **Privacy:** privacy policy URL; `NSHealthShareUsageDescription` string; App Privacy "nutrition label" (Health & Fitness + identifiers, not linked to ads); confirm no third-party sharing of health data.
- **Encryption at rest:** SQLCipher on every per-user DB + the identity DB — **in scope for launch** (see B6).
- TestFlight beta → fixes → submit.

---

## 7. Cross-cutting

- **Secrets/config:** new env vars — `SESSION_JWT_SECRET`, `DB_ENCRYPTION_MASTER_KEY`, `APPLE_BUNDLE_ID`, `GOOGLE_OAUTH_CLIENT_ID`, `ADMIN_ADOPT_EMAIL`, `DATA_DIR` (already exists). All in the secrets manager. Remove `HEALTHKIT_API_KEY`, `STRAVA_*` (keep dormant behind flag).
- **CORS/hosting:** `main.py` CORS currently localhost-only — add the production WebView origin (or `capacitor://`/`null` handling for the WKWebView). Confirm the persistent volume on Railway/Fly is sized for many per-user DBs.
- **Testing:** the `seeded_backend` fixture (`conftest.py`) must seed *per-user* DBs and exercise `get_current_user` (inject a fake user). Add tests: token verification (mock JWKS), cross-tenant isolation (user A can't read user B), account deletion purges files, legacy adoption runs once.
- **Observability:** structured logs keyed by `user_id`; per-user `sync_log` already exists.
- **Rollout:** ship behind the existing deploy; Aaron is user #0 via `ADMIN_ADOPT_EMAIL` to validate adoption before external TestFlight.

---

## 8. Sequencing & estimate

| Order | Workstream | Depends on | Est. |
|---|---|---|---|
| 1 | A1–A4 backend identity + session | — | 4–5 d |
| 2 | B1–B5 per-user data layer + registry | A4 (needs user_id) | 4–6 d |
| 3 | B4 legacy adoption | B1–B3 | 1 d |
| 4 | A5 iOS auth + WebView token | A1–A4 | 3–4 d |
| 5 | C1–C4 HealthKit rebuild | A5 | 4–5 d |
| 6 | D branding/onboarding | A5 | 3–4 d (parallel) |
| 7 | E compliance | A–C | 3–4 d |

**~5–6 calendar weeks** for one engineer to TestFlight; A+B are the critical path and should not be parallelized away.

---

## 9. Open decisions for the engineer to confirm

1. **Auth library:** `pyjwt[crypto]` vs `python-jose` for JWKS verification (either is fine; pick one, add to deps).
2. **Session length / revocation:** 30-day JWT + `/refresh` proposed; keep the `sessions` table for revocation or drop it for pure-stateless? (Recommend keep — needed for "sign out everywhere" + deletion.)
3. **WebView token transport:** `localStorage` injection (specced) vs cookie store. Confirm `api.js` change is acceptable.
4. **Master-key custody:** see **Appendix C** — recommendation is platform secrets + offline escrow at launch behind a `KeyProvider` seam, KMS envelope as fast-follow. Final call: env-now vs KMS-now.
5. **Connection cap** N for `DataServiceRegistry` eviction — set based on expected concurrent users.

---

## Appendix C — Master-key custody & rotation

The master key (`DB_ENCRYPTION_MASTER_KEY`) unwraps every per-user DEK, which decrypts every per-user DB. It is the single most sensitive secret in the system: **lose it → all user data is unrecoverable; leak it (with disk access) → all user data is exposed.**

### What encryption-at-rest does and doesn't buy us
- ✅ **Protects:** stolen disk/volume, leaked snapshots/backups, the hosting provider or an insider reading the raw volume, a discarded drive.
- ❌ **Does NOT protect:** a live, code-execution-compromised server (the running process can read the key from memory and decrypt). That's inherent to at-rest encryption — accept it; defend the host separately. The goal here is "data on disk is useless without a secret that does not live on that disk."

**Design rule:** the master key must never sit on the same volume as the DBs. All three options below honor that.

### Option 1 — Platform secrets (Railway/Fly env)  ·  *recommended for launch*
Master key injected as an env var; read once at boot into memory.
- **Pros:** zero new infra, free, key is off the data volume, ships today.
- **Cons:** plaintext in the host env + process memory; anyone with deploy/console access can read it; no access audit; manual rotation; backup is "remember to copy it."
- **Mitigations (required):** generate once with `openssl rand -hex 32`; store in **two** durable places — the platform secret **and** an offline copy in Aaron's password manager (escrow); never regenerate casually; restrict who has deploy/console access.

### Option 2 — KMS envelope encryption  ·  *recommended fast-follow*
A cloud KMS (AWS KMS, GCP KMS, or Vault Transit) holds a **Key-Encryption-Key (KEK)** that *never leaves the KMS*. The master key (a Data-Encryption-Key) is stored **wrapped by the KEK**; at boot the app calls KMS once to unwrap it into memory.
- **Pros:** access is IAM-scoped and **audit-logged**; KEK never exposed; KEK rotation re-wraps only the single master DEK (no DB churn); versioning/backup handled by the provider.
- **Cons:** new dependency at boot (KMS down = app can't start — cache the unwrapped master in memory and fail closed); small cost (AWS KMS ≈ $1/key/mo + per-request); IAM setup.
- **Why fast-follow not launch:** adds infra + a boot-time external call; not worth blocking TestFlight on, but should land before meaningful user volume.

### Option 3 — Wrapped per-user DEKs (the key *model*, independent of 1 vs 2)
Already folded into spec §B6. Random DEK per user, stored wrapped (AES-GCM) by the master in the identity DB. Combine with whichever custody option above.
- **Why it matters:** with plain `HKDF(master, salt=user_id)`, rotating the master means `PRAGMA rekey` on **every** per-user DB — O(total data), slow, risky, and racy against live writes. With wrapped DEKs, rotating the master only **re-wraps N small rows** — O(users), fast, no DB rewrite. It also enables revoking/rotating a single user's key.

### Recommended path
1. **Launch:** Option 1 (platform secret) **+** Option 3 (wrapped DEKs) **+** a `KeyProvider` abstraction (`get_master() -> bytes`) so the source of the master is one swappable function.
2. **Fast-follow:** implement a KMS-backed `KeyProvider` (Option 2) — a drop-in because everything went through the seam.

### Rotation runbook (with wrapped DEKs)
- **Rotate master:** stand up `master_v2`; for each user, unwrap DEK with `master_v1`, re-wrap with `master_v2`, update the row; flip the active master; keep `v1` until all rows migrated. Per-user DBs are **never** touched.
- **Rotate a single user's DEK** (e.g., suspected exposure): `PRAGMA rekey` on that one DB + re-wrap. This replaces the blunt `rekey_dbs.py` (COMP-4) with a targeted, online operation.

### Non-negotiables
- Master key generated once, escrowed in ≥2 durable locations, **never** committed.
- A written recovery runbook (where the key lives, how to restore).
- `KeyProvider` seam from day one so custody can change without touching call sites.
