import WidgetKit
import SwiftUI
import Security

// PLT-1 — Readiness widget: home-screen (small/medium) + lock-screen
// (circular/rectangular). Fetches /api/stats/readiness + /api/health/summary
// with the device token from the shared keychain group; falls back to the
// last cached snapshot when the network (or a locked keychain) says no.

// MARK: - Snapshot model

struct ReadinessSnapshot: Codable {
    let score: Int
    let zone: String
    let why: String?
    let rhrDelta: Double?      // vs 30-day avg, bpm
    let hrvDelta: Double?      // vs 30-day avg, ms
    let sleepHours: Double?    // last night
    let fetchedAt: Date

    static let placeholder = ReadinessSnapshot(
        score: 72, zone: "ready", why: nil,
        rhrDelta: -2.0, hrvDelta: 5.0, sleepHours: 7.4, fetchedAt: .now)
}

// MARK: - API + cache

enum WidgetAPI {
    // The widget is a separate binary — these must mirror the app's
    // Config.backendURL / AuthService.tokenKey / KeychainHelper.service.
    // The keychain service is the APP's bundle id (Bundle.main here would
    // give the widget's own id and find nothing).
    static let backendURL = "https://workout-viz.fly.dev"
    static let keychainService = "Aaronlytics.WorkoutViz"
    static let tokenKey = "session_jwt"
    private static let cacheKey = "readinessSnapshotCache"

    static func token() -> String? {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: tokenKey,
            kSecReturnData as String:  true,
            kSecMatchLimit as String:  kSecMatchLimitOne,
        ]
        var result: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func get<T: Decodable>(_ path: String, token: String, as type: T.Type) async -> T? {
        guard let url = URL(string: "\(backendURL)\(path)") else { return nil }
        var req = URLRequest(url: url)
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.timeoutInterval = 15
        guard let (data, response) = try? await URLSession.shared.data(for: req),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    static func fetchSnapshot() async -> ReadinessSnapshot? {
        guard let token = token() else { return nil }

        struct Readiness: Decodable { let score: Int; let zone: String; let why: String? }
        struct Summary: Decodable {
            struct Metric: Decodable {
                let metric: String
                let today: Double
                let vs_30d_avg: Double?
            }
            let metrics: [Metric]
        }

        guard let r = await get("/api/stats/readiness", token: token, as: Readiness.self) else {
            return nil
        }
        let summary = await get("/api/health/summary", token: token, as: Summary.self)
        func m(_ slug: String) -> Summary.Metric? {
            summary?.metrics.first { $0.metric == slug }
        }
        let snap = ReadinessSnapshot(
            score: r.score, zone: r.zone, why: r.why,
            rhrDelta: m("resting_heartrate")?.vs_30d_avg,
            hrvDelta: m("hrv_sdnn")?.vs_30d_avg,
            sleepHours: m("sleep_asleep")?.today,
            fetchedAt: .now)
        cache(snap)
        return snap
    }

    static func cache(_ snap: ReadinessSnapshot) {
        if let data = try? JSONEncoder().encode(snap) {
            UserDefaults.standard.set(data, forKey: cacheKey)
        }
    }

    static func cached() -> ReadinessSnapshot? {
        guard let data = UserDefaults.standard.data(forKey: cacheKey) else { return nil }
        return try? JSONDecoder().decode(ReadinessSnapshot.self, from: data)
    }
}

// MARK: - Timeline

struct ReadinessEntry: TimelineEntry {
    let date: Date
    let snap: ReadinessSnapshot?
    let stale: Bool
}

struct ReadinessProvider: TimelineProvider {
    func placeholder(in context: Context) -> ReadinessEntry {
        ReadinessEntry(date: .now, snap: .placeholder, stale: false)
    }

    func getSnapshot(in context: Context, completion: @escaping (ReadinessEntry) -> Void) {
        if context.isPreview {
            completion(placeholder(in: context))
            return
        }
        completion(ReadinessEntry(date: .now, snap: WidgetAPI.cached(), stale: false))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<ReadinessEntry>) -> Void) {
        Task {
            let fetched = await WidgetAPI.fetchSnapshot()
            let snap = fetched ?? WidgetAPI.cached()
            let entry = ReadinessEntry(date: .now, snap: snap, stale: fetched == nil && snap != nil)
            // Fresh data → check back in 2h; failed fetch → retry sooner.
            let next = Date().addingTimeInterval(fetched != nil ? 2 * 3600 : 30 * 60)
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }
}

// MARK: - Presentation helpers

enum Zone {
    static func color(_ zone: String) -> Color {
        switch zone {
        case "peak":     return Color(red: 0.29, green: 0.87, blue: 0.50)
        case "ready":    return Color(red: 0.22, green: 0.74, blue: 0.97)
        case "moderate": return Color(red: 0.98, green: 0.75, blue: 0.14)
        case "easy":     return Color(red: 0.98, green: 0.57, blue: 0.24)
        case "recovery": return Color(red: 0.97, green: 0.44, blue: 0.44)
        default:         return .gray
        }
    }

    static func label(_ zone: String) -> String {
        switch zone {
        case "peak":     return "Peak Form"
        case "ready":    return "Ready"
        case "moderate": return "Moderate"
        case "easy":     return "Tired"
        case "recovery": return "Recovery"
        default:         return zone.capitalized
        }
    }
}

private func fmtSigned(_ v: Double, decimals: Int = 0) -> String {
    let s = String(format: "%+.\(decimals)f", v)
    return s == "+0" || s == "-0" ? "0" : s
}

private func fmtSleep(_ h: Double) -> String {
    let hh = Int(h)
    let mm = Int(round((h - Double(hh)) * 60))
    return "\(hh)h \(String(format: "%02d", mm))m"
}

// MARK: - Views

struct ReadinessWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: ReadinessEntry

    var body: some View {
        Group {
            if let snap = entry.snap {
                switch family {
                case .accessoryCircular:    circular(snap)
                case .accessoryRectangular: rectangular(snap)
                case .systemMedium:         medium(snap)
                default:                    small(snap)
                }
            } else {
                setup
            }
        }
        .containerBackground(for: .widget) { Color(red: 0.05, green: 0.05, blue: 0.06) }
    }

    private var setup: some View {
        VStack(spacing: 4) {
            Image(systemName: "heart.text.square")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("Open Volken to set up")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
    }

    private func circular(_ snap: ReadinessSnapshot) -> some View {
        Gauge(value: Double(snap.score), in: 0...100) {
            Text("RDY")
        } currentValueLabel: {
            Text("\(snap.score)").fontWeight(.bold)
        }
        .gaugeStyle(.accessoryCircular)
        .tint(Zone.color(snap.zone))
    }

    private func rectangular(_ snap: ReadinessSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("Readiness \(snap.score) · \(Zone.label(snap.zone))")
                .font(.headline)
            Text(deltaLine(snap))
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func small(_ snap: ReadinessSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text("READINESS")
                    .font(.system(size: 9, weight: .bold))
                    .tracking(1.2)
                    .foregroundStyle(.secondary)
                Spacer()
                if entry.stale {
                    Image(systemName: "wifi.slash")
                        .font(.system(size: 8))
                        .foregroundStyle(.tertiary)
                }
            }
            Text("\(snap.score)")
                .font(.system(size: 42, weight: .heavy, design: .rounded))
                .foregroundStyle(Zone.color(snap.zone))
                .minimumScaleFactor(0.6)
            Text(Zone.label(snap.zone))
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(Zone.color(snap.zone))
            Spacer(minLength: 2)
            Text(deltaLine(snap))
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func medium(_ snap: ReadinessSnapshot) -> some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 2) {
                Text("READINESS")
                    .font(.system(size: 9, weight: .bold))
                    .tracking(1.2)
                    .foregroundStyle(.secondary)
                Text("\(snap.score)")
                    .font(.system(size: 46, weight: .heavy, design: .rounded))
                    .foregroundStyle(Zone.color(snap.zone))
                Text(Zone.label(snap.zone))
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(Zone.color(snap.zone))
            }
            Rectangle()
                .fill(Zone.color(snap.zone).opacity(0.25))
                .frame(width: 1)
            VStack(alignment: .leading, spacing: 6) {
                if let d = snap.rhrDelta {
                    statRow(label: "Resting HR", value: "\(fmtSigned(d, decimals: 1)) bpm",
                            good: d <= 0)
                }
                if let d = snap.hrvDelta {
                    statRow(label: "HRV", value: "\(fmtSigned(d)) ms", good: d >= 0)
                }
                if let h = snap.sleepHours {
                    statRow(label: "Sleep", value: fmtSleep(h), good: h >= 7)
                }
                HStack(spacing: 3) {
                    Text("as of")
                    Text(snap.fetchedAt, style: .time)
                    if entry.stale { Text("· offline") }
                }
                .font(.system(size: 8))
                .foregroundStyle(.tertiary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private func statRow(label: String, value: String, good: Bool) -> some View {
        HStack(spacing: 6) {
            Circle()
                .fill(good ? Color(red: 0.29, green: 0.87, blue: 0.50)
                           : Color(red: 0.98, green: 0.57, blue: 0.24))
                .frame(width: 5, height: 5)
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.primary)
        }
    }

    private func deltaLine(_ snap: ReadinessSnapshot) -> String {
        var bits: [String] = []
        if let d = snap.hrvDelta { bits.append("HRV \(fmtSigned(d))ms") }
        if let d = snap.rhrDelta { bits.append("RHR \(fmtSigned(d, decimals: 1))") }
        if let h = snap.sleepHours { bits.append("Sleep \(fmtSleep(h))") }
        return bits.isEmpty ? "vs your 30-day baselines" : bits.joined(separator: " · ")
    }
}

// MARK: - Widget declaration

struct ReadinessWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "VolkenReadiness", provider: ReadinessProvider()) { entry in
            ReadinessWidgetView(entry: entry)
        }
        .configurationDisplayName("Readiness")
        .description("Your readiness score with this morning's body signals.")
        .supportedFamilies([.systemSmall, .systemMedium,
                            .accessoryCircular, .accessoryRectangular])
    }
}

@main
struct VolkenWidgetBundle: WidgetBundle {
    var body: some Widget {
        ReadinessWidget()
    }
}
