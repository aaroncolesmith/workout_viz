import Foundation

enum Config {
    static let backendURL = ProcessInfo.processInfo.environment["BACKEND_URL"]
        ?? "https://workout-viz.fly.dev"

    /// How many workouts to send per batch
    static let syncBatchSize = 50

    /// Days to look back on the initial sync after first sign-in (≈ 6 months).
    /// The user can trigger a deeper "Load 2 years" backfill from Settings.
    static let initialSyncDays = 182
}
