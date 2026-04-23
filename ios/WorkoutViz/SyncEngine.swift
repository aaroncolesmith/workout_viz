import Foundation
import Combine
import HealthKit
import CoreLocation

/// Coordinates HealthKit reads → backend POST.  Singleton, observable.
@MainActor
final class SyncEngine: ObservableObject {
    static let shared = SyncEngine()

    @Published var isSyncing = false
    @Published var syncProgress: String = ""
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
        if let last = lastSyncDate, Date().timeIntervalSince(last) < 1800 { return }
        await performSync()
    }

    func performSync() async {
        guard !isSyncing, hk.isAvailable else { return }
        isSyncing = true
        syncProgress = "Starting…"
        defer {
            isSyncing = false
            syncProgress = ""
        }

        let since: Date
        if let last = lastSyncDate {
            since = last
        } else {
            since = Calendar.current.date(
                byAdding: .day, value: -Config.initialSyncDays, to: Date()
            )!
        }

        do {
            let workouts = try await hk.fetchWorkouts(since: since)
            guard !workouts.isEmpty else {
                recordSync()
                return
            }

            // Partition: GPS workouts get streams (posted one at a time);
            //            non-GPS workouts are batched without streams.
            var nonGPSBatch: [HKWorkoutRequest] = []
            var done = 0
            let total = workouts.count

            for workout in workouts {
                done += 1
                syncProgress = "Syncing \(done)/\(total)…"

                let (avgHR, maxHR) = try await hk.fetchHeartRate(for: workout)
                var req = HKWorkoutRequest.from(workout: workout, avgHR: avgHR, maxHR: maxHR)

                if workout.workoutActivityType.isGPS {
                    // GPS: fetch route + HR series, attach as streams, POST alone.
                    let locations = (try? await hk.fetchRoute(for: workout)) ?? []
                    let hrSeries = (try? await hk.fetchHeartRateSeries(for: workout)) ?? []

                    if !locations.isEmpty {
                        req.streams = Self.buildStreams(
                            workoutStart: workout.startDate,
                            locations: locations,
                            hrSeries: hrSeries
                        )
                    }
                    try await postBatch([req])
                } else {
                    nonGPSBatch.append(req)
                    if nonGPSBatch.count >= Config.syncBatchSize {
                        try await postBatch(nonGPSBatch)
                        nonGPSBatch.removeAll()
                    }
                }
            }

            if !nonGPSBatch.isEmpty {
                try await postBatch(nonGPSBatch)
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

    private func postBatch(_ payloads: [HKWorkoutRequest]) async throws {
        guard let url = URL(string: "\(Config.backendURL)/api/import/healthkit") else { return }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(Config.healthkitAPIKey, forHTTPHeaderField: "X-Api-Key")
        req.httpBody = try JSONEncoder().encode(HKSyncBody(workouts: payloads))
        req.timeoutInterval = 120  // streams can take a moment to process

        let (_, response) = try await URLSession.shared.data(for: req)
        if let http = response as? HTTPURLResponse, http.statusCode >= 400 {
            throw URLError(.badServerResponse)
        }
    }

    /// Build the streams payload: relative timestamps + downsampled series.
    private static func buildStreams(
        workoutStart: Date,
        locations: [CLLocation],
        hrSeries: [(Date, Double)]
    ) -> HKStreams {
        // GPS is typically already ~1 Hz; no downsample needed for sub-3-hour workouts.
        let locs = locations.map { loc -> HKLocationSample in
            HKLocationSample(
                t: loc.timestamp.timeIntervalSince(workoutStart),
                lat: loc.coordinate.latitude,
                lng: loc.coordinate.longitude,
                alt: loc.altitude
            )
        }
        let hrs = hrSeries.map { (date, bpm) -> HKHeartRateSample in
            HKHeartRateSample(t: date.timeIntervalSince(workoutStart), bpm: bpm)
        }
        return HKStreams(locations: locs, heartrate: hrs)
    }
}

// MARK: - Data models (match backend Pydantic schema)

private struct HKLocationSample: Codable {
    let t: Double
    let lat: Double
    let lng: Double
    let alt: Double?
}

private struct HKHeartRateSample: Codable {
    let t: Double
    let bpm: Double
}

private struct HKStreams: Codable {
    let locations: [HKLocationSample]
    let heartrate: [HKHeartRateSample]
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
    var streams: HKStreams?

    static func from(workout: HKWorkout, avgHR: Double?, maxHR: Double?) -> HKWorkoutRequest {
        let iso = ISO8601DateFormatter()
        return HKWorkoutRequest(
            source_id: workout.uuid.uuidString,
            type: workout.workoutActivityType.backendType,
            start_date: iso.string(from: workout.startDate),
            end_date: iso.string(from: workout.endDate),
            duration_sec: workout.duration,
            distance_meters: workout.totalDistance?.doubleValue(for: .meter()),
            active_energy_kcal: workout.totalEnergyBurned?.doubleValue(for: .kilocalorie()),
            avg_heartrate: avgHR,
            max_heartrate: maxHR,
            streams: nil
        )
    }
}

private struct HKSyncBody: Codable {
    let workouts: [HKWorkoutRequest]
}
