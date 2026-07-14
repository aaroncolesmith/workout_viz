import Combine
import Foundation
import UserNotifications

/// Post-sync workout notifications (CMP-5).
///
/// After a just-finished workout uploads, we fetch its comparison verdict and
/// post a local notification — "Run analyzed: Your 2nd fastest of 8 on
/// Riverside Loop" — deep-linking to the activity page.  This is the moment
/// that makes Volken the app you open right after a workout.
///
/// Permission is requested **contextually**: the first time we actually have
/// a verdict to deliver, never at launch.  If the user declines, we stay
/// silent forever (the system won't re-prompt, and neither do we).
///
/// Foreground behaviour: no banner while the app is open — the verdict card
/// is already on screen.
@MainActor
final class NotificationManager: NSObject, ObservableObject {
    static let shared = NotificationManager()

    /// Web-app path from a tapped notification ("/activity/123");
    /// consumed by the WebView, which navigates and clears it.
    @Published var pendingDeepLink: String?

    private override init() { super.init() }

    /// Install as the notification-center delegate. Called once at app start.
    func setup() {
        UNUserNotificationCenter.current().delegate = self
    }

    // MARK: - Morning readiness report (RDY-3)

    /// Opt-in via the Account sheet.  Fired by the sleep-data HK observer, so
    /// the report lands right after the night's sleep syncs — a report that
    /// doesn't yet know about last night is worse than none.
    static let morningReportKey = "morningReportEnabled"
    private let lastMorningReportKey = "lastMorningReportDay"

    var morningReportEnabled: Bool {
        UserDefaults.standard.bool(forKey: Self.morningReportKey)
    }

    /// Toggle handler: enabling asks for notification permission (returns
    /// false if declined, so the UI can snap the toggle back).
    func setMorningReportEnabled(_ enabled: Bool) async -> Bool {
        if enabled {
            guard await ensurePermission() else { return false }
        }
        UserDefaults.standard.set(enabled, forKey: Self.morningReportKey)
        return true
    }

    func morningReadinessReportIfNeeded() async {
        guard morningReportEnabled else { return }
        let hour = Calendar.current.component(.hour, from: Date())
        guard (4...11).contains(hour) else { return }   // mornings only

        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        let todayKey = f.string(from: Date())
        guard UserDefaults.standard.string(forKey: lastMorningReportKey) != todayKey else { return }

        // Never prompt from a background wake — only post if already allowed.
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        guard settings.authorizationStatus == .authorized else { return }

        guard let r = await fetchReadiness() else { return }
        UserDefaults.standard.set(todayKey, forKey: lastMorningReportKey)

        let content = UNMutableNotificationContent()
        content.title = "Readiness \(r.score) — \(Self.zoneLabel(r.zone))"
        content.body = r.why ?? r.recommendation
        content.sound = .default
        content.userInfo = ["path": "/"]
        try? await UNUserNotificationCenter.current().add(
            UNNotificationRequest(identifier: "morning-\(todayKey)", content: content, trigger: nil))
    }

    private struct ReadinessResp: Decodable {
        let score: Int
        let zone: String
        let recommendation: String
        let why: String?
    }

    private func fetchReadiness() async -> ReadinessResp? {
        guard let url = URL(string: "\(Config.backendURL)/api/stats/readiness") else { return nil }
        let req = AuthService.shared.authorizedRequest(url: url, timeout: 20)
        do {
            let (data, response) = try await URLSession.shared.data(for: req)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { return nil }
            return try JSONDecoder().decode(ReadinessResp.self, from: data)
        } catch {
            return nil
        }
    }

    private static func zoneLabel(_ zone: String) -> String {
        switch zone {
        case "peak":     return "Peak Form"
        case "ready":    return "Ready"
        case "moderate": return "Moderate"
        case "easy":     return "Tired"
        case "recovery": return "Recovery"
        default:         return zone.capitalized
        }
    }

    // MARK: - Posting

    func notifyWorkoutAnalyzed(activityId: Int, workoutType: String) async {
        guard await ensurePermission() else { return }

        let verdict = await fetchVerdict(activityId: activityId)
        let content = UNMutableNotificationContent()
        content.title = "\(workoutType) analyzed"
        content.body = verdict ?? "Tap to see how it compares with your history."
        content.sound = .default
        content.userInfo = ["path": "/activity/\(activityId)"]

        let request = UNNotificationRequest(
            identifier: "workout-\(activityId)", content: content, trigger: nil)
        try? await UNUserNotificationCenter.current().add(request)
    }

    private func ensurePermission() async -> Bool {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        switch settings.authorizationStatus {
        case .notDetermined:
            // Contextual first ask: we have a verdict in hand right now.
            return (try? await center.requestAuthorization(options: [.alert, .sound])) ?? false
        case .denied:
            return false
        default:
            return true
        }
    }

    private func fetchVerdict(activityId: Int) async -> String? {
        guard let url = URL(string: "\(Config.backendURL)/api/activities/\(activityId)/comparison") else {
            return nil
        }
        let req = AuthService.shared.authorizedRequest(url: url, timeout: 20)
        do {
            let (data, response) = try await URLSession.shared.data(for: req)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { return nil }
            struct Resp: Decodable { let verdict: String? }
            return try JSONDecoder().decode(Resp.self, from: data).verdict
        } catch {
            return nil
        }
    }
}

// MARK: - UNUserNotificationCenterDelegate

extension NotificationManager: UNUserNotificationCenterDelegate {
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let path = response.notification.request.content.userInfo["path"] as? String
        Task { @MainActor in
            if let path { self.pendingDeepLink = path }
            completionHandler()
        }
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([])   // app is open — the verdict card is on screen
    }
}
