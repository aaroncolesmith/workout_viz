import SwiftUI

@main
struct WorkoutVizApp: App {
    @StateObject private var syncEngine = SyncEngine.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(syncEngine)
                .onReceive(NotificationCenter.default.publisher(
                    for: UIApplication.didBecomeActiveNotification)
                ) { _ in
                    // Sync fresh data whenever the app comes to foreground
                    Task { await syncEngine.syncIfNeeded() }
                }
        }
    }
}
