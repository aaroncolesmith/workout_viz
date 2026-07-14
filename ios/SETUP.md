# iOS Companion App — Setup

## What this is
A SwiftUI wrapper that:
1. Embeds your Fly.io-hosted web app in a full-screen WKWebView
2. Syncs HealthKit workouts to the backend automatically on foreground

## Prerequisites
- Xcode 15+
- An Apple Developer account (free works for personal device testing)
- Your Fly.io app deployed (see `fly.toml` in repo root)

---

## Part 1 — Fly.io Deployment

### 1. Install flyctl and log in
```bash
brew install flyctl
flyctl auth login
```

### 2. Create the app and persistent volume
```bash
flyctl apps create workout-viz
flyctl volumes create workout_data --app workout-viz --region ewr --size 3 --yes
```

### 3. Set secrets
```bash
flyctl secrets set \
  DB_ENCRYPTION_MASTER_KEY=$(openssl rand -hex 32) \
  --app workout-viz
```

Keep an offline backup of `DB_ENCRYPTION_MASTER_KEY` — losing it makes all
user data unrecoverable. To rotate it later, see
`backend/scripts/rotate_master_key.py`.

### 4. Deploy
```bash
flyctl deploy --app workout-viz
```

### 5. Note your URL
`https://workout-viz.fly.dev`

---

## Part 2 — Xcode Project

### 1. Create the project
- Xcode → New Project → iOS → App
- Product Name: `WorkoutViz`
- Interface: SwiftUI
- Language: Swift
- Bundle ID: `com.yourname.workoutviz`

### 2. Add the Swift source files
Drag all files from `ios/WorkoutViz/` into the Xcode project (or open the
checked-in `ios/WorkoutViz.xcodeproj` directly):
- `WorkoutVizApp.swift` — replace the generated App file
- `ContentView.swift` — replace the generated ContentView
- `HealthKitManager.swift`
- `SyncEngine.swift`
- `AuthService.swift`, `AccountView.swift`, `KeychainHelper.swift`
- `Config.swift`

### 3. Update Config.swift
The backend URL should already point to Fly.io. Verify:
```swift
static let backendURL = "https://workout-viz.fly.dev"
```
There's no sign-in flow: on first launch the app silently registers a device
token with the backend (`POST /api/auth/device`) and stores it in the
Keychain forever. No Apple/Google account, no bundle-id-matching secret to
configure.

### 4. Add capabilities
- Select your target → Signing & Capabilities → + Capability → HealthKit
  (leave "Clinical Health Records" unchecked)
- Do **not** add "Sign in with Apple" — it requires a paid Apple Developer
  Program membership and this app doesn't use it.

### 5. Add Info.plist keys
Add these two keys under your target's Info tab:
```
NSHealthShareUsageDescription  →  "WorkoutViz reads your workouts to display fitness trends."
NSHealthUpdateUsageDescription →  "WorkoutViz does not write health data."
```

### 6. Set your development team
Target → Signing & Capabilities → Team → your Apple ID

### 7. Run on your iPhone
- Connect your iPhone via USB
- Select your device as the run target
- Press Run (⌘R)
- Trust the developer certificate on your iPhone: Settings → General → VPN & Device Management

---

## How syncing works

1. On first launch the app silently registers a device token with the
   backend (`POST /api/auth/device`); the token is stored in the Keychain and
   injected into the WKWebView — no user interaction
2. App requests HealthKit permission, then runs an anchored incremental sync
   (initial window: last ~6 months; "Load 2 years" backfill available)
3. Workouts are POSTed to `POST /api/import/healthkit` in batches of 50 with
   the Bearer token; deletions in HealthKit are mirrored to the backend
4. The HealthKit anchor only advances when every upload/deletion succeeded,
   so transient failures are retried on the next sync
5. On every foreground the app re-registers if it somehow lost its token,
   then syncs

## Strava (dormant)

Strava ingestion is shelved. Its routes only register when the
`STRAVA_AUTH_ENABLED=true` secret is set, along with the `STRAVA_*` vars in
`.env.example`.
