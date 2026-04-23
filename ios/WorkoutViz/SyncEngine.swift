import Foundation
import Combine
import HealthKit

/// Coordinates HealthKit reads → backend POST.  Singleton, observable.
@MainActor
final class SyncEngine: ObservableObject {
    static let shared = SyncEngine()

    @Published var isSyncing = false
    @Published var lastSyncDate: Date? = {
        UserDefaults.standard.object(forKey: "lastSyncDate") as? Date
    }()

    private let hk = HealthKitManager.shared

    // MARK: - Public

    func requestPermissionsIfNeeded() async {
        guard hk.isAvailable else { return }
        try? await hk.requestAuthorization()
        await syncIfNeeded()
    }

    func syncIfNeeded() async {
        // Throttle: don't sync more than once per 30 minutes
        if let last = lastSyncDate, Date().timeIntervalSince(last) < 1800 { return }
        await performSync()
    }

    func performSync() async {
        guard !isSyncing, hk.isAvailable else { return }
        isSyncing = true
        defer { isSyncing = false }

        let since: Date
        if let last = lastSyncDate {
            since = last
        } else {
            since = Calendar.current.date(
                byAdding: .day,
                value: -Config.initialSyncDays,
                to: Date()
            )!
        }

        do {
            let workouts = try await hk.fetchWorkouts(since: since)
            guard !workouts.isEmpty else {
                recordSync()
                return
            }

            // Enrich with HR data, then batch-POST
            var payloads: [HKWorkoutPayload] = []
            for workout in workouts {
                let (avg, max) = try await hk.fetchHeartRate(for: workout)
                payloads.append(HKWorkoutPayload(workout: workout, avgHR: avg, maxHR: max))
            }

            let batches = stride(from: 0, to: payloads.count, by: Config.syncBatchSize).map {
                Array(payloads[$0 ..< min($0 + Config.syncBatchSize, payloads.count)])
            }

            for batch in batches {
                try await postBatch(batch)
            }

            recordSync()
        } catch {
            print("[SyncEngine] sync failed: \(error)")
        }
    }

    // MARK: - Private

    private func recordSync() {
        let now = Date()
        lastSyncDate = now
        UserDefaults.standard.set(now, forKey: "lastSyncDate")
    }

    private func postBatch(_ payloads: [HKWorkoutPayload]) async throws {
        guard let url = URL(string: "\(Config.backendURL)/api/import/healthkit") else { return }

        let body = HKSyncBody(workouts: payloads.map { $0.toRequest() })
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(Config.healthkitAPIKey, forHTTPHeaderField: "X-Api-Key")
        req.httpBody = try JSONEncoder().encode(body)

        let (_, response) = try await URLSession.shared.data(for: req)
        if let http = response as? HTTPURLResponse, http.statusCode >= 400 {
            throw URLError(.badServerResponse)
        }
    }
}

// MARK: - Data models

private struct HKWorkoutPayload {
    let workout: HKWorkout
    let avgHR: Double?
    let maxHR: Double?

    func toRequest() -> HKWorkoutRequest {
        let distM: Double? = workout.totalDistance?.doubleValue(for: .meter())
        return HKWorkoutRequest(
            source_id: workout.uuid.uuidString,
            type: workout.workoutActivityType.backendType,
            start_date: ISO8601DateFormatter().string(from: workout.startDate),
            end_date: ISO8601DateFormatter().string(from: workout.endDate),
            duration_sec: workout.duration,
            distance_meters: distM,
            active_energy_kcal: workout.totalEnergyBurned?.doubleValue(for: .kilocalorie()),
            avg_heartrate: avgHR,
            max_heartrate: maxHR
        )
    }
}

private struct HKWorkoutRequest: Codable {
    let source_id: String
    let type: String
    let start_date: String
    let end_date: String
    let duration_sec: Double
    let distance_meters: Double?
    let active_energy_kcal: Double?
    let avg_heartrate: Double?
    let max_heartrate: Double?
}

private struct HKSyncBody: Codable {
    let workouts: [HKWorkoutRequest]
}
