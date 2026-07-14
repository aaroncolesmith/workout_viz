# Engineering Tickets — Multi-Tenant Launch

> Companion to `ENGINEERING_SPEC.md` (detail) and `LAUNCH_ROADMAP.md` (product).
> Each ticket is sized ~0.5–3 days. IDs are stable; copy into Linear/GitHub as-is.
> **Estimates** are dev-days for one engineer. **Deps** = blocking ticket IDs.

## Labels
`epic:sec` `epic:auth` `epic:ios` `epic:data` `epic:healthkit` `epic:brand` `epic:compliance` · `type:feat` `type:refactor` `type:chore` `type:security` · `P0` (launch-blocking) `P1` (launch) `P2` (fast-follow)

## Suggested sequencing
1. **SEC-1** (do today) → 2. **AUTH-1…5** → 3. **DATA-1…7** → 4. **IOS-1…3** → 5. **HK-1…4** → 6. **BRAND-1…3** (parallel) → 7. **COMP-1…4**.
Critical path: AUTH → DATA → IOS → HK. Do not parallelize AUTH/DATA away.

---

# EPIC SEC — Security hygiene

### SEC-1 · Rotate & remove the committed HealthKit API key `P0` `type:security`
**Why:** `ios/WorkoutViz/Config.swift:9` hardcodes a live `HEALTHKIT_API_KEY`, committed to git.
**Do:**
- Rotate the server-side key now (invalidate the leaked one).
- Remove the literal from `Config.swift` (read from env/xcconfig only) until the shared-key path is deleted in HK-3.
- If the repo will ever be public, scrub from git history (`git filter-repo`).
**Acceptance:** No secret literals in tracked source; leaked key no longer accepted by the server.
**Est:** 0.5

### SEC-2 · Provision launch secrets `P0` `type:chore` · Deps: —
**Do:** Add to the secrets manager (Railway/Fly): `SESSION_JWT_SECRET` (32B random), `DB_ENCRYPTION_MASTER_KEY` (32B random, **escrowed/backed up**), `APPLE_BUNDLE_ID`, `GOOGLE_OAUTH_CLIENT_ID`, `ADMIN_ADOPT_EMAIL`. Document each in `.env.example`. Confirm master-key backup (open decision #4).
**Acceptance:** App boots reading all new vars; `.env.example` updated; master key has a documented backup location.
**Est:** 0.5

---

# EPIC AUTH — Identity & Auth (backend)

### AUTH-1 · Central identity DB `P0` `type:feat` · Deps: —
**Do:** New `backend/services/identity_db.py` — `init_identity_db()` + `get_identity_conn()` (thread-local, mirrors `database.py`). Create `users`, `identities`, `sessions` tables per spec §A1. Encrypt with master key (salt `"identity"`, see DATA-6).
**Acceptance:** Tables created at startup; a row can be inserted/read; file is SQLCipher-encrypted.
**Est:** 1

### AUTH-2 · Apple & Google ID-token verification `P0` `type:feat` · Deps: SEC-2
**Do:** `backend/services/auth_providers.py`. Verify Apple (`appleid.apple.com/auth/keys`, `aud=APPLE_BUNDLE_ID`) and Google (`oauth2/v3/certs`, `aud=GOOGLE_OAUTH_CLIENT_ID`) ID tokens: signature, `iss`, `aud`, `exp`. JWKS fetched + cached. Add `pyjwt[crypto]` (or `python-jose`) to requirements.
**Acceptance:** Valid token → `(provider, sub, email)`; tampered/expired/wrong-aud → raises. Unit tests mock JWKS.
**Est:** 2

### AUTH-3 · Session JWT issue/verify/refresh `P0` `type:feat` · Deps: AUTH-1, SEC-2
**Do:** `backend/services/session.py` — HS256 with `SESSION_JWT_SECRET`, claims `sub,jti,iat,exp(30d)`; persist `jti` in `sessions`; `verify()` checks sig+exp+jti-not-revoked; `refresh()` within 7d of expiry.
**Acceptance:** Issued token verifies; revoking `jti` → 401; refresh returns a new token + rotates `jti`.
**Est:** 1

### AUTH-4 · Login endpoints + user resolution `P0` `type:feat` · Deps: AUTH-2, AUTH-3, DATA-2
**Do:** Rewrite `backend/api/auth.py`: `POST /api/auth/apple`, `POST /api/auth/google`, `POST /api/auth/refresh`, `GET /api/auth/me`. On verify: upsert `identities`→`users`; **create the per-user DB** on first login (DATA-2); update `last_login_at`; return `{access_token, expires_at, user}`. Gate old Strava routes behind a dormant flag.
**Acceptance:** New provider login creates exactly one user + per-user DB; repeat login reuses it; `/me` returns the caller.
**Est:** 1.5

### AUTH-5 · `get_current_user` dependency `P0` `type:feat` · Deps: AUTH-3
**Do:** `backend/api/deps.py` — FastAPI dependency parsing `Authorization: Bearer`, verifying via session.py, returning `user_id`; 401 otherwise.
**Acceptance:** Missing/bad token → 401; valid → `user_id` injected. Covered by tests.
**Est:** 0.5

---

# EPIC DATA — Multi-tenant data layer + encryption

### DATA-1 · Path-keyed connections + SQLCipher in `database.py` `P0` `type:refactor` · Deps: SEC-2
**Do:** Per spec §B1+§B6. `get_conn(db_path)` thread-local **map**; `init_db(db_path)` takes path param. Swap `sqlite3` → `sqlcipher3-binary`; apply `PRAGMA key`/`cipher_compatibility=4` before other PRAGMAs. Add `close_conns(db_path)`. Verify Docker builds the wheel.
**Acceptance:** Two paths → two independent encrypted DBs in one thread; plain `sqlite3` can't open them; existing schema/migration fns run against a passed path.
**Est:** 2

### DATA-2 · KeyProvider + wrapped per-user DEKs + DB provisioning `P0` `type:feat` · Deps: DATA-1, AUTH-1
**Do:** Per spec §B6 + Appendix C. `KeyProvider` seam (`get_master() -> bytes`, env-backed for launch). Generate a random 32B DEK per user, store it **wrapped** (AES-GCM by master) in the identity DB; at connect, unwrap → `PRAGMA key` with the DEK. Helper to create/open `DATA_DIR/users/<uid>/workouts.db` (schema init on create). Used by AUTH-4.
**Acceptance:** Fresh user → random DEK wrapped in identity DB + encrypted workout DB created; same id reopens via unwrap; distinct ids → distinct DEKs/files; master never touches the data volume; all key access flows through `KeyProvider`.
**Est:** 1.5

### DATA-3 · `DataService(user_id)` per-user `P0` `type:refactor` · Deps: DATA-2
**Do:** `__init__(self, user_id)` sets `self.db_path`, owns its own `_TTLCache`; replace ~40 `get_conn()` calls with `get_conn(self.db_path)`. Move the per-user extended-PR backfill trigger into `__init__` gated by that user's `user_settings` flag (remove the global startup job).
**Acceptance:** Methods read/write only that user's DB; no module-level `get_conn()` calls remain; backfill runs once per user.
**Est:** 2

### DATA-4 · `DataServiceRegistry` + lifecycle `P0` `type:feat` · Deps: DATA-3
**Do:** `get_data_service(user_id)` → LRU registry (cap N), lock-guarded; evict closes that user's connections. `main.py` startup only calls `init_identity_db()` (drop global warm-up). Remove/scope `/api/cache/*`.
**Acceptance:** Concurrent access to many users stays under the connection cap; eviction closes handles; startup no longer touches a global workouts.db.
**Est:** 1.5

### DATA-5 · Scope every route to `get_current_user` `P0` `type:refactor` · Deps: AUTH-5, DATA-4
**Do:** Add `user_id = Depends(get_current_user)` + `get_data_service(user_id)` to all routes in `activities.py`, `routes.py`, `import_routes.py`. Add a CI grep/lint failing on any zero-arg `get_data_service()`.
**Acceptance:** Two tokens → disjoint data on every endpoint; CI fails if an unscoped call is reintroduced.
**Est:** 1.5

### DATA-6 · Encrypt identity DB `P1` `type:feat` · Deps: DATA-1, AUTH-1
**Do:** Apply SQLCipher (salt `"identity"`) to `users.db`.
**Acceptance:** `users.db` unreadable without the master key.
**Est:** 0.5

### DATA-7 · Legacy DB adopt + encrypt-on-import `P0` `type:feat` · Deps: DATA-2
**Do:** Per spec §B4+§B6. On first login matching `ADMIN_ADOPT_EMAIL`, if a legacy plaintext `DATA_DIR/workouts.db` exists and no per-user DB yet → `ATTACH … KEY`, `sqlcipher_export`, `DETACH`, delete plaintext. Also ship `backend/scripts/adopt_legacy_db.py`.
**Acceptance:** Aaron's history appears under his user, encrypted; plaintext original removed; runs exactly once.
**Est:** 1

---

# EPIC IOS — iOS auth & WebView session

### IOS-1 · Sign in with Apple + Google `P0` `type:feat` · Deps: AUTH-4
**Do:** `ASAuthorizationAppleIDProvider` + `GoogleSignIn` SDK. POST tokens to `/api/auth/{apple,google}`. Store session JWT in **Keychain**. Add Apple capability + Google URL scheme. (Apple Sign-In mandatory since Google is offered.)
**Acceptance:** Both providers sign in on device; token persists across relaunch; sign-out clears Keychain.
**Est:** 2

### IOS-2 · Native auth gate + WebView token injection `P0` `type:feat` · Deps: IOS-1
**Do:** No token → native sign-in screen, don't load WebView. With token → inject `WKUserScript` setting `localStorage.session_token`. Update `frontend/src/utils/api.js` to send `Authorization: Bearer` from that token + handle 401 → signal shell to re-auth.
**Acceptance:** WebView only loads when authed; all `/api` calls carry the JWT; 401 forces re-auth.
**Est:** 1.5

### IOS-3 · Swap ingest auth to Bearer `P0` `type:refactor` · Deps: IOS-1, HK-3
**Do:** `SyncEngine`/`Config` send `Authorization: Bearer` instead of `X-Api-Key`; delete `healthkitAPIKey`. Reset anchor + synced-id set on logout/account switch.
**Acceptance:** Ingest authenticated by JWT only; switching accounts doesn't leak the previous user's sync state.
**Est:** 1

---

# EPIC HEALTHKIT — Data-fetching rebuild

### HK-1 · 6-month default + "Load 2 years" `P1` `type:feat` · Deps: —
**Do:** `Config.initialSyncDays 365→182`; add Settings/onboarding "Load 2 years" → `performSync(force:true, since: 2y)`. Demote 10-year backfill to a hidden debug action.
**Acceptance:** First sync pulls ~6 months; "Load 2 years" extends history; backfill stays resumable.
**Est:** 1

### HK-2 · Anchored incremental + background delivery `P1` `type:feat` · Deps: —
**Do:** `HKAnchoredObjectQuery` over `workoutType()` with a persisted **per-user** `HKQueryAnchor`; `HKObserverQuery` + `enableBackgroundDelivery(.immediate)`. Add `com.apple.developer.healthkit.background-delivery` entitlement + Background Modes. Handle `deletedObjects` → backend delete.
**Acceptance:** New Watch workout syncs within minutes with app backgrounded; deletions propagate; anchor persists.
**Est:** 2.5

### HK-3 · User-scoped ingest endpoint `P0` `type:refactor` · Deps: AUTH-5, DATA-5
**Do:** `POST /api/import/healthkit` + `/healthkit/missing-streams`: drop `X-Api-Key`/`_require_healthkit_key`; use `get_current_user` → `get_data_service(user_id)`. Delete `HEALTHKIT_API_KEY` env after cutover.
**Acceptance:** Ingest writes only to the authed user's DB; shared-key path removed.
**Est:** 1

### HK-4 · Workout-deletion endpoint `P2` `type:feat` · Deps: HK-3
**Do:** `DELETE /api/activities/{id}` (user-scoped) for HealthKit `deletedObjects` from HK-2.
**Acceptance:** Deleting on the Watch removes it server-side for that user only.
**Est:** 0.5

---

# EPIC BRAND — Branding & onboarding

### BRAND-1 · `APP_NAME` wiring `P1` `type:chore` · Deps: —
**Do:** Single source of truth for the name across frontend, iOS display name, and `main.py` `app` string. Final name TBD — make the rename one line.
**Acceptance:** Changing one constant updates all surfaces.
**Est:** 0.5

### BRAND-2 · App icon, launch screen, logo, share-card branding `P1` `type:feat` · Deps: BRAND-1
**Acceptance:** Real icon + launch screen on device; logo in WebView header; share cards branded.
**Est:** 2

### BRAND-3 · Onboarding flow `P1` `type:feat` · Deps: IOS-2, HK-1
**Do:** Sign in → grant HealthKit → "Importing your last 6 months…" progress → Dashboard. Apply `design/DESIGN.md` premium pass.
**Acceptance:** First-run is a guided native flow; WebView appears only after auth + sync kickoff.
**Est:** 3

---

# EPIC COMPLIANCE — App Store gating

### COMP-1 · Account deletion `P0` `type:feat` · Deps: DATA-5
**Do:** `DELETE /api/account` → purge `users/<uid>/` dir + registry rows + sessions. Native "Delete account" in Settings → calls it → signs out.
**Acceptance:** Deletion fully removes the user's files + identity; in-app; irreversible.
**Est:** 1

### COMP-2 · Data export `P1` `type:feat` · Deps: DATA-5
**Do:** `GET /api/account/export` → zip the user's `workouts.db` + JSON manifest.
**Acceptance:** Export downloads the caller's data only.
**Est:** 1

### COMP-3 · Privacy policy + Health usage strings + nutrition label `P0` `type:chore` · Deps: —
**Do:** Privacy policy URL; `NSHealthShareUsageDescription`; App Privacy nutrition label (Health & Fitness + identifiers, not linked to ads, no third-party sharing).
**Acceptance:** Info.plist + App Store Connect privacy section complete.
**Est:** 1

### COMP-4 · Key-rotation tooling `P2` `type:chore` · Deps: DATA-2
**Do:** With wrapped DEKs, master rotation = re-wrap N DEK rows (no DB rewrite). Script: unwrap each DEK with `master_v1` → re-wrap with `master_v2` → update row. Plus a targeted single-user `PRAGMA rekey` path. See Appendix C runbook.
**Acceptance:** Master rotation re-wraps all DEKs without touching per-user DBs; single-user rekey works online; verified on a copy.
**Est:** 1

### COMP-5 · KMS-backed KeyProvider `P2` `type:security` · Deps: DATA-2
**Do:** Fast-follow custody upgrade (Appendix C Option 2). Implement a KMS-backed `KeyProvider` (AWS/GCP KMS or Vault Transit) using envelope encryption — KEK in KMS, master unwrapped once at boot, cached in memory, fail-closed if KMS unreachable. Drop-in via the DATA-2 seam.
**Acceptance:** App boots sourcing the master from KMS with no call-site changes; KMS access is audit-logged; KEK rotation re-wraps only the master.
**Est:** 1.5

---

# EPIC QA — Cross-cutting tests

### QA-1 · Multi-tenant test harness `P0` `type:chore` · Deps: DATA-5
**Do:** Update `seeded_backend` (`conftest.py`) to seed **per-user** encrypted DBs + a fake `get_current_user`. Tests: cross-tenant isolation (A can't read B), token verification (mocked JWKS), deletion purges files, legacy adoption runs once, encrypted files unreadable by plain sqlite3.
**Acceptance:** Suite green; isolation + encryption asserted in CI.
**Est:** 2

---

## Totals (rough)
SEC 1 · AUTH 6 · DATA 9.5 · IOS 4.5 · HK 5.5 · BRAND 5.5 · COMP 4 · QA 2 ≈ **~38 dev-days** → ~5–6 calendar weeks for one engineer including review/QA, matching the roadmap.
