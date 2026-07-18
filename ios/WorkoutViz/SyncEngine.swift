import Foundation
import Combine
import HealthKit
import CoreLocation

/// Coordinates HealthKit reads → backend POST.  Singleton, observable.
///
/// Incremental sync (HK-2): uses HKAnchoredObjectQuery so only workouts added
/// or deleted since the last run are processed.  The anchor is stored in the
/// Keychain (per-user — cleared on sign-out) under the key "hk_anchor".
///
/// Background delivery: HKObserverQuery fires when HealthKit has new data.
/// Requires UIBackgroundModes: ["healthkit"] — enable via Xcode's
/// "Signing & Capabilities → HealthKit → Background Delivery" toggle.
@MainActor
final class SyncEngine: ObservableObject {
    static let shared = SyncEngine()

    @Published var isSyncing = false
    @Published var syncProgress: String = ""
    @Published var showingAccount = false
    @Published var gapDetected = false
    @Published var lastSyncDate: Date? = {
        UserDefaults.standard.object(forKey: "lastSyncDate") as? Date
    }()

    private let hk = HealthKitManager.shared
    private let anchorKey = "hk_anchor"

    // Persisted set of source_ids we've already uploaded (used for force-retry logic).
    private let syncedKey = "syncedSourceIds"
    private var syncedSourceIds: Set<String> = {
        Set(UserDefaults.standard.stringArray(forKey: "syncedSourceIds") ?? [])
    }()

    private let chunkSize = 25

    /// How far back a full backfill reaches, and thus the only window gap
    /// detection may fairly compare against — HealthKit history older than
    /// this is out of scope for the app and must never count as "missing".
    private var backfillCutoff: Date {
        Calendar.current.date(byAdding: .year, value: -2, to: Date())!
    }

    // MARK: - Public

    func requestPermissionsIfNeeded() async {
        guard hk.isAvailable else { return }
        try? await hk.requestAuthorization()
        hk.registerWorkoutObserver { [weak self] in
            guard let self else { return }
            Task { await self.performSync() }
        }
        // Sleep arriving = the user woke up: sync the night's metrics, then
        // the morning readiness report (RDY-3, opt-in) has fresh data.
        hk.registerSleepObserver {
            Task {
                await MetricsSyncEngine.shared.sync()
                await NotificationManager.shared.morningReadinessReportIfNeeded()
            }
        }
        await syncIfNeeded()
    }

    func syncIfNeeded() async {
        if let last = lastSyncDate, Date().timeIntervalSince(last) < 1800 { return }
        await performSync()
        await checkForGap()
    }

    /// Full historical backfill — resets anchor, goes back 2 years, re-uploads
    /// everything the backend says is missing splits.
    func performFullBackfill() async {
        gapDetected = false
        try? await hk.requestAuthorization()
        print("[SyncEngine] route auth = \(hk.routeAuthStatus.rawValue)")

        // Clear anchor so the anchored query returns all historical workouts.
        KeychainHelper.delete(key: anchorKey)

        let forceRetryKeys = await fetchMissingStreamKeys()
        print("[SyncEngine] backend reports \(forceRetryKeys.count) workouts missing splits")

        await performSync(force: true, since: backfillCutoff, forceRetryKeys: forceRetryKeys)
        await checkForGap()
    }

    /// Compares the local HealthKit workout count against what the backend
    /// has synced, both bounded to `backfillCutoff` — comparing unbounded
    /// HealthKit history against a sync that only ever reaches 2 years back
    /// would flag a "gap" no backfill could ever close. A shortfall within
    /// that window (most commonly from an interrupted backfill — the anchor
    /// only advances on full success) means workouts exist on the phone that
    /// never reached the server. Surfaces a one-tap prompt instead of
    /// requiring the user to remember Settings → Backfill HealthKit.
    private func checkForGap() async {
        guard let hkCount = try? await hk.countWorkouts(since: backfillCutoff) else { return }
        guard let url = URL(string: "\(Config.backendURL)/api/import/healthkit/coverage") else { return }
        let req = AuthService.shared.authorizedRequest(url: url, timeout: 20)
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            struct Resp: Decodable { let count: Int }
            let backendCount = try JSONDecoder().decode(Resp.self, from: data).count
            gapDetected = hkCount > backendCount
        } catch {
            print("[SyncEngine] coverage check failed: \(error)")
        }
    }

    /// Reset backfill progress so next backfill re-uploads everything.
    func resetBackfillProgress() {
        syncedSourceIds.removeAll()
        UserDefaults.standard.removeObject(forKey: syncedKey)
        KeychainHelper.delete(key: anchorKey)
        MetricsSyncEngine.shared.resetProgress()
    }

    // MARK: - Core sync

    func performSync(
        force: Bool = false,
        since overrideSince: Date? = nil,
        forceRetryKeys: Set<String> = []
    ) async {
        guard !isSyncing, hk.isAvailable else { return }
        isSyncing = true
        syncProgress = "Starting…"
        defer { isSyncing = false; syncProgress = "" }

        // Daily health metrics ride along on every workout sync — they change
        // every day even when no workout does (BIO-3).
        await MetricsSyncEngine.shared.sync(force: force, since: overrideSince)

        // Load saved anchor; nil on first run.
        let savedAnchor = loadAnchor()

        // Predicate: only needed when there's no anchor yet (limits initial scope).
        let predicate: NSPredicate?
        if savedAnchor == nil {
            let since = overrideSince ?? Calendar.current.date(
                byAdding: .day, value: -Config.initialSyncDays, to: Date()
            )!
            predicate = HKQuery.predicateForSamples(
                withStart: since, end: nil, options: .strictStartDate)
        } else {
            predicate = nil  // anchor covers everything since last sync
        }

        let result: HealthKitManager.AnchoredResult
        do {
            result = try await hk.fetchWorkoutsAnchored(anchor: savedAnchor, predicate: predicate)
        } catch {
            print("[SyncEngine] fetchWorkoutsAnchored failed: \(error)")
            return
        }

        // Any failed upload or deletion means the anchor must NOT advance:
        // an anchored query never re-returns objects once the anchor moves
        // past them, so advancing on failure silently drops workouts forever.
        var hadFailures = false

        // ── Handle deletions ──────────────────────────────────────────────────
        if !result.deletedUUIDs.isEmpty {
            syncProgress = "Removing \(result.deletedUUIDs.count) deleted workout(s)…"
            await withTaskGroup(of: Bool.self) { group in
                for uuid in result.deletedUUIDs {
                    group.addTask { await self.deleteActivityBySource(uuid) }
                }
                for await ok in group where !ok { hadFailures = true }
            }
        }

        // ── Handle new/updated workouts ───────────────────────────────────────
        let workouts = result.workouts
        let pending: [HKWorkout]
        if forceRetryKeys.isEmpty && !force {
            pending = workouts.filter { !syncedSourceIds.contains($0.uuid.uuidString) }
        } else {
            pending = workouts.filter { w in
                if syncedSourceIds.contains(w.uuid.uuidString) {
                    let key = "\(w.workoutActivityType.backendType)|\(Self.minuteKey(w.startDate))"
                    if forceRetryKeys.contains(key) {
                        syncedSourceIds.remove(w.uuid.uuidString)
                        return true
                    }
                    return false
                }
                return true
            }
        }

        let total = pending.count
        let alreadyDone = workouts.count - total

        if total == 0 && result.deletedUUIDs.isEmpty {
            syncProgress = "Up to date"
            recordSync()
            saveAnchor(result.anchor)
            return
        }

        var done = 0
        var addedActivities: [HKAddedActivity] = []
        for chunkStart in stride(from: 0, to: pending.count, by: chunkSize) {
            let end = min(chunkStart + chunkSize, pending.count)
            let chunk = Array(pending[chunkStart..<end])
            let (failures, added) = await processChunk(chunk) { completed in
                done += completed
                let skippedLabel = alreadyDone > 0 ? " (\(alreadyDone) already done)" : ""
                self.syncProgress = "Syncing \(done)/\(total)\(skippedLabel)"
            }
            addedActivities += added
            if failures > 0 { hadFailures = true }
            commitSyncedIds()
        }

        if hadFailures {
            // Keep the old anchor: the next sync re-queries from it and retries
            // the failed items (successes are skipped via syncedSourceIds).
            print("[SyncEngine] upload/deletion failures — keeping old anchor for retry")
        } else {
            saveAnchor(result.anchor)
        }
        recordSync()

        // CMP-5: notify for a just-finished workout. Incremental syncs only —
        // a backfill of two years of history is not "your run is ready".
        if !force, !addedActivities.isEmpty {
            let idBySource = Dictionary(
                addedActivities.map { ($0.source_id, $0.id) },
                uniquingKeysWith: { first, _ in first }
            )
            let cutoff = Date().addingTimeInterval(-6 * 3600)
            if let recent = pending
                .filter({ $0.startDate > cutoff && idBySource[$0.uuid.uuidString] != nil })
                .max(by: { $0.startDate < $1.startDate }) {
                await NotificationManager.shared.notifyWorkoutAnalyzed(
                    activityId: idBySource[recent.uuid.uuidString]!,
                    workoutType: recent.workoutActivityType.backendType
                )
            }
        }
    }

    // MARK: - Anchor persistence

    private func loadAnchor() -> HKQueryAnchor? {
        guard let data = KeychainHelper.loadData(key: anchorKey) else { return nil }
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: data)
    }

    private func saveAnchor(_ anchor: HKQueryAnchor) {
        guard let data = try? NSKeyedArchiver.archivedData(
            withRootObject: anchor, requiringSecureCoding: true
        ) else { return }
        KeychainHelper.saveData(data, key: anchorKey)
    }

    // MARK: - Deletion

    /// Returns true only when the backend confirmed the deletion.
    private func deleteActivityBySource(_ uuid: UUID) async -> Bool {
        guard let url = URL(string: "\(Config.backendURL)/api/activities/source/\(uuid.uuidString)") else { return false }
        let req = AuthService.shared.authorizedRequest(url: url, method: "DELETE", timeout: 15)
        do {
            let (_, response) = try await URLSession.shared.data(for: req)
            if let http = response as? HTTPURLResponse, http.statusCode >= 400 {
                print("[SyncEngine] delete \(uuid) failed: HTTP \(http.statusCode)")
                return false
            }
            return true
        } catch {
            print("[SyncEngine] delete \(uuid) failed: \(error)")
            return false
        }
    }

    // MARK: - Missing-streams check (for force-retry on backfill)

    private func fetchMissingStreamKeys() async -> Set<String> {
        guard let url = URL(string: "\(Config.backendURL)/api/import/healthkit/missing-streams") else {
            return []
        }
        let req = AuthService.shared.authorizedRequest(url: url, timeout: 30)

        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            struct Resp: Decodable {
                struct Item: Decodable { let type: String; let start_date: String }
                let activities: [Item]
            }
            let decoded = try JSONDecoder().decode(Resp.self, from: data)
            let iso = ISO8601DateFormatter()
            var keys: Set<String> = []
            for item in decoded.activities {
                guard let d = iso.date(from: item.start_date) else { continue }
                keys.insert("\(item.type)|\(Self.minuteKey(d))")
            }
            return keys
        } catch {
            print("[SyncEngine] fetchMissingStreamKeys failed: \(error)")
            return []
        }
    }

    private static func minuteKey(_ d: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm"
        f.timeZone = TimeZone(identifier: "UTC")
        return f.string(from: d)
    }

    // MARK: - Chunk processing

    /// Returns the number of workouts whose upload failed (caller must not
    /// advance the HealthKit anchor when this is non-zero) plus the backend
    /// ids of newly inserted activities (for the CMP-5 notification).
    private func processChunk(
        _ workouts: [HKWorkout],
        onProgress: (Int) -> Void
    ) async -> (failures: Int, added: [HKAddedActivity]) {
        var failures = 0
        var added: [HKAddedActivity] = []
        var nonGPSBatch: [(HKWorkoutRequest, String)] = []

        for workout in workouts {
            let sourceId = workout.uuid.uuidString
            do {
                let (avgHR, maxHR) = try await hk.fetchHeartRate(for: workout)
                var req = HKWorkoutRequest.from(workout: workout, avgHR: avgHR, maxHR: maxHR)

                if workout.workoutActivityType.isGPS {
                    let locations = (try? await hk.fetchRoute(for: workout)) ?? []
                    let hrSeries  = (try? await hk.fetchHeartRateSeries(for: workout)) ?? []
                    let distanceSeries = locations.isEmpty
                        ? ((try? await hk.fetchDistanceSeries(for: workout)) ?? [])
                        : []

                    let gotStreams = !locations.isEmpty || !distanceSeries.isEmpty
                    if gotStreams {
                        req.streams = Self.buildStreams(
                            workoutStart: workout.startDate,
                            locations: locations,
                            distanceSeries: distanceSeries,
                            hrSeries: hrSeries
                        )
                    } else {
                        print("[SyncEngine] no streams for GPS workout \(sourceId) — will retry")
                    }
                    added += try await postBatch([req])
                    if gotStreams { syncedSourceIds.insert(sourceId) }
                    onProgress(1)
                } else {
                    nonGPSBatch.append((req, sourceId))
                }
            } catch {
                failures += 1
                print("[SyncEngine] upload failed for \(sourceId): \(error)")
            }
        }

        if !nonGPSBatch.isEmpty {
            do {
                added += try await postBatch(nonGPSBatch.map { $0.0 })
                for (_, sid) in nonGPSBatch { syncedSourceIds.insert(sid) }
                onProgress(nonGPSBatch.count)
            } catch {
                failures += nonGPSBatch.count
                print("[SyncEngine] non-GPS batch POST failed: \(error)")
            }
        }
        return (failures, added)
    }

    private func commitSyncedIds() {
        UserDefaults.standard.set(Array(syncedSourceIds), forKey: syncedKey)
    }

    private func recordSync() {
        let now = Date()
        lastSyncDate = now
        UserDefaults.standard.set(now, forKey: "lastSyncDate")
    }

    @discardableResult
    private func postBatch(_ payloads: [HKWorkoutRequest]) async throws -> [HKAddedActivity] {
        guard let url = URL(string: "\(Config.backendURL)/api/import/healthkit") else { return [] }
        var req = AuthService.shared.authorizedRequest(url: url, method: "POST", timeout: 120)
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(HKSyncBody(workouts: payloads))

        let (data, response) = try await URLSession.shared.data(for: req)
        if let http = response as? HTTPURLResponse, http.statusCode >= 400 {
            throw URLError(.badServerResponse)
        }
        let decoded = try? JSONDecoder().decode(HKSyncResponseBody.self, from: data)
        return decoded?.added_activities ?? []
    }

    private static func buildStreams(
        workoutStart: Date,
        locations: [CLLocation],
        distanceSeries: [(Date, Double)],
        hrSeries: [(Date, Double)]
    ) -> HKStreams {
        HKStreams(
            locations: locations.map {
                HKLocationSample(t: $0.timestamp.timeIntervalSince(workoutStart),
                                 lat: $0.coordinate.latitude,
                                 lng: $0.coordinate.longitude,
                                 alt: $0.altitude)
            },
            distance: distanceSeries.map {
                HKDistanceSample(t: $0.0.timeIntervalSince(workoutStart), m: $0.1)
            },
            heartrate: hrSeries.map {
                HKHeartRateSample(t: $0.0.timeIntervalSince(workoutStart), bpm: $0.1)
            }
        )
    }
}

// MARK: - Data models (match backend Pydantic schema)

private struct HKLocationSample: Codable {
    let t: Double; let lat: Double; let lng: Double; let alt: Double?
}
private struct HKHeartRateSample: Codable {
    let t: Double; let bpm: Double
}
private struct HKDistanceSample: Codable {
    let t: Double; let m: Double
}
private struct HKStreams: Codable {
    let locations: [HKLocationSample]
    let distance:  [HKDistanceSample]
    let heartrate: [HKHeartRateSample]
}
private struct HKWorkoutRequest: Codable {
    let source_id:          String
    let type:               String
    let start_date:         String
    let end_date:           String
    let duration_sec:       Double
    let distance_meters:    Double?
    let active_energy_kcal: Double?
    let avg_heartrate:      Double?
    let max_heartrate:      Double?
    var streams:            HKStreams?

    static func from(workout: HKWorkout, avgHR: Double?, maxHR: Double?) -> HKWorkoutRequest {
        let iso = ISO8601DateFormatter()
        return HKWorkoutRequest(
            source_id:          workout.uuid.uuidString,
            type:               workout.workoutActivityType.backendType,
            start_date:         iso.string(from: workout.startDate),
            end_date:           iso.string(from: workout.endDate),
            duration_sec:       workout.duration,
            distance_meters:    workout.totalDistance?.doubleValue(for: .meter()),
            active_energy_kcal: workout.statistics(for: HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned)!)?
                .sumQuantity()?.doubleValue(for: .kilocalorie()),
            avg_heartrate:      avgHR,
            max_heartrate:      maxHR,
            streams:            nil
        )
    }
}
private struct HKSyncBody: Codable {
    let workouts: [HKWorkoutRequest]
}
private struct HKAddedActivity: Decodable {
    let id: Int
    let source_id: String
}
private struct HKSyncResponseBody: Decodable {
    let added_activities: [HKAddedActivity]?
}
