import Foundation
import Combine
import HealthKit
import CoreLocation

/// Coordinates HealthKit reads → backend POST.  Singleton, observable.
///
/// Resumable backfill: each workout we successfully upload gets its UUID
/// recorded in UserDefaults. Tapping "Backfill" again after an interruption
/// skips already-uploaded workouts and continues from the next one, so
/// progress accumulates across runs.
@MainActor
final class SyncEngine: ObservableObject {
    static let shared = SyncEngine()

    @Published var isSyncing = false
    @Published var syncProgress: String = ""
    @Published var lastSyncDate: Date? = {
        UserDefaults.standard.object(forKey: "lastSyncDate") as? Date
    }()

    private let hk = HealthKitManager.shared

    // Persistent set of source_ids (HKWorkout UUIDs) we've successfully uploaded.
    private let syncedKey = "syncedSourceIds"
    private var syncedSourceIds: Set<String> = {
        let arr = UserDefaults.standard.stringArray(forKey: "syncedSourceIds") ?? []
        return Set(arr)
    }()

    /// Backfill chunk size — how many workouts to process before committing
    /// progress to UserDefaults. Smaller = more frequent commits, more resilience
    /// to interruptions. GPS workouts are expensive (route + HR fetch per),
    /// so 25 is a good tradeoff between progress and UI responsiveness.
    private let chunkSize = 25

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

    /// Full historical backfill — ignores lastSyncDate and goes back 10 years.
    /// Resumable: already-uploaded workouts are skipped based on persisted UUIDs.
    func performFullBackfill() async {
        // Re-request auth in case workoutRoute wasn't granted earlier — iOS
        // will silently no-op if the user already approved everything.
        try? await hk.requestAuthorization()
        print("[SyncEngine] route auth status = \(hk.routeAuthStatus.rawValue) " +
              "(0=notDetermined, 1=denied, 2=authorized — read auth may always show 0)")
        await performSync(force: true, since: tenYearsAgo())
    }

    /// Reset backfill progress so next backfill re-uploads everything.
    func resetBackfillProgress() {
        syncedSourceIds.removeAll()
        UserDefaults.standard.removeObject(forKey: syncedKey)
    }

    private func tenYearsAgo() -> Date {
        Calendar.current.date(byAdding: .year, value: -10, to: Date())!
    }

    func performSync(force: Bool = false, since overrideSince: Date? = nil) async {
        guard !isSyncing, hk.isAvailable else { return }
        isSyncing = true
        syncProgress = "Starting…"
        defer {
            isSyncing = false
            syncProgress = ""
        }

        let since: Date
        if let o = overrideSince {
            since = o
        } else if let last = lastSyncDate, !force {
            since = last
        } else {
            since = Calendar.current.date(
                byAdding: .day, value: -Config.initialSyncDays, to: Date()
            )!
        }

        let workouts: [HKWorkout]
        do {
            workouts = try await hk.fetchWorkouts(since: since)
        } catch {
            print("[SyncEngine] fetchWorkouts failed: \(error)")
            return
        }
        guard !workouts.isEmpty else {
            recordSync()
            return
        }

        // Skip anything we've already uploaded — enables resumable backfill.
        let pending = workouts.filter { !syncedSourceIds.contains($0.uuid.uuidString) }
        let total = pending.count
        let alreadyDone = workouts.count - total

        if total == 0 {
            syncProgress = "Nothing new"
            recordSync()
            return
        }

        // Process in chunks. Progress commits after every chunk, so
        // an interruption still leaves the completed chunks persisted.
        var done = 0
        for chunkStart in stride(from: 0, to: pending.count, by: chunkSize) {
            let end = min(chunkStart + chunkSize, pending.count)
            let chunk = Array(pending[chunkStart..<end])

            await processChunk(chunk) { completed in
                done += completed
                let remaining = total - done
                let skippedLabel = alreadyDone > 0 ? " (\(alreadyDone) already done)" : ""
                self.syncProgress = "Syncing \(done)/\(total)\(skippedLabel) — \(remaining) left"
            }

            // Persist after each chunk so a crash / background / network loss
            // doesn't throw away the work we just did.
            commitSyncedIds()
        }

        recordSync()
    }

    // MARK: - Private

    /// Process up to `chunkSize` workouts. Records each successfully-uploaded
    /// workout's UUID in the in-memory set; caller persists to UserDefaults.
    /// Per-workout errors are caught so one bad workout doesn't abort the chunk.
    private func processChunk(
        _ workouts: [HKWorkout],
        onProgress: (Int) -> Void
    ) async {
        var nonGPSBatch: [(HKWorkoutRequest, String)] = []  // (request, source_id)

        for workout in workouts {
            let sourceId = workout.uuid.uuidString

            do {
                let (avgHR, maxHR) = try await hk.fetchHeartRate(for: workout)
                var req = HKWorkoutRequest.from(workout: workout, avgHR: avgHR, maxHR: maxHR)

                if workout.workoutActivityType.isGPS {
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
                    syncedSourceIds.insert(sourceId)
                    onProgress(1)
                } else {
                    nonGPSBatch.append((req, sourceId))
                }
            } catch {
                // Record but continue with the next workout.
                print("[SyncEngine] upload failed for workout \(sourceId): \(error)")
            }
        }

        // Flush accumulated non-GPS workouts for this chunk.
        if !nonGPSBatch.isEmpty {
            do {
                try await postBatch(nonGPSBatch.map { $0.0 })
                for (_, sid) in nonGPSBatch {
                    syncedSourceIds.insert(sid)
                }
                onProgress(nonGPSBatch.count)
            } catch {
                print("[SyncEngine] non-GPS batch POST failed: \(error)")
            }
        }
    }

    private func commitSyncedIds() {
        UserDefaults.standard.set(Array(syncedSourceIds), forKey: syncedKey)
    }

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
        req.timeoutInterval = 120

        let (_, response) = try await URLSession.shared.data(for: req)
        if let http = response as? HTTPURLResponse, http.statusCode >= 400 {
            throw URLError(.badServerResponse)
        }
    }

    private static func buildStreams(
        workoutStart: Date,
        locations: [CLLocation],
        hrSeries: [(Date, Double)]
    ) -> HKStreams {
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
