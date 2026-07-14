import SwiftUI

@main
struct WorkoutVizApp: App {
    @StateObject private var authService = AuthService.shared
    @StateObject private var syncEngine = SyncEngine.shared
    @StateObject private var notificationManager = NotificationManager.shared

    init() {
        NotificationManager.shared.setup()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authService)
                .environmentObject(syncEngine)
                .environmentObject(notificationManager)
                .task {
                    await authService.registerDeviceIfNeeded()
                }
                .onReceive(NotificationCenter.default.publisher(
                    for: UIApplication.didBecomeActiveNotification)
                ) { _ in
                    Task {
                        await authService.registerDeviceIfNeeded()
                        if authService.isAuthenticated {
                            await syncEngine.syncIfNeeded()
                        }
                    }
                }
        }
    }
}
