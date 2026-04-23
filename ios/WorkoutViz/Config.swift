import Foundation

enum Config {
    /// Your Railway deployment URL — update after first deploy.
    /// Example: "https://workout-viz-production.up.railway.app"
    static let backendURL = ProcessInfo.processInfo.environment["BACKEND_URL"]
        ?? "https://workoutviz-production.up.railway.app"

    /// Must match HEALTHKIT_API_KEY env var set in Railway
    static let healthkitAPIKey = ProcessInfo.processInfo.environment["HEALTHKIT_API_KEY"]
        ?? "change-me-in-railway"

    /// How many workouts to send per batch
    static let syncBatchSize = 50

    /// Sync workouts from this many days back on first launch
    static let initialSyncDays = 365
}
