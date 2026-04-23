# iOS Companion App — Setup

## What this is
A SwiftUI wrapper that:
1. Embeds your Railway-hosted web app in a full-screen WKWebView
2. Syncs HealthKit workouts to the backend automatically on foreground

## Prerequisites
- Xcode 15+
- An Apple Developer account (free works for personal device testing)
- Your Railway app deployed (see `/RAILWAY.md`)

---

## Part 1 — Railway Deployment

### 1. Push to GitHub
```bash
git add Dockerfile .dockerignore railway.toml
git commit -m "Add Railway deployment config"
git push
```

### 2. Create Railway project
1. Go to railway.app → New Project → Deploy from GitHub repo
2. Select your `workout_viz` repo
3. Railway detects the `Dockerfile` automatically

### 3. Configure environment variables in Railway
| Variable | Value |
|---|---|
| `STRAVA_CLIENT_ID` | From strava.com/settings/api |
| `STRAVA_CLIENT_SECRET` | From strava.com/settings/api |
| `STRAVA_REDIRECT_URI` | `https://YOUR-APP.up.railway.app/auth/callback` |
| `HEALTHKIT_API_KEY` | Any strong random string (e.g. `openssl rand -hex 32`) |

### 4. Add a persistent volume
In Railway: your service → Volumes → Mount at `/data`

### 5. Note your Railway URL
It looks like: `https://workout-viz-production.up.railway.app`

---

## Part 2 — Xcode Project

### 1. Create the project
- Xcode → New Project → iOS → App
- Product Name: `WorkoutViz`
- Interface: SwiftUI
- Language: Swift
- Bundle ID: `com.yourname.workoutviz`

### 2. Add the Swift source files
Drag all files from `ios/WorkoutViz/` into the Xcode project:
- `WorkoutVizApp.swift` — replace the generated App file
- `ContentView.swift` — replace the generated ContentView
- `HealthKitManager.swift`
- `SyncEngine.swift`
- `Config.swift`

### 3. Update Config.swift
Edit the two constants:
```swift
static let backendURL = "https://YOUR-APP.up.railway.app"
static let healthkitAPIKey = "the-key-you-set-in-railway"
```

### 4. Add HealthKit capability
- Select your target → Signing & Capabilities → + Capability → HealthKit
- Check "Clinical Health Records" is NOT checked (we don't need it)

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

1. On first launch, app requests HealthKit permission
2. Fetches workouts from the last 365 days, enriches each with HR samples
3. POSTs to `POST /api/import/healthkit` in batches of 50
4. On every foreground, syncs any workouts newer than the last sync (throttled to max once per 30 min)
5. After sync completes, refresh the web view to see new data

## Strava OAuth in the app

The web app's Strava OAuth flow (`/auth/callback`) needs the Railway URL as the redirect URI. Update it:
1. Go to strava.com/settings/api
2. Set Authorization Callback Domain to your Railway domain (e.g. `workout-viz-production.up.railway.app`)
3. Update `STRAVA_REDIRECT_URI` in Railway env vars to match
