import Foundation
import HealthKit

/// Syncs daily health metrics (BIO-3) — resting HR, HRV, sleep, VO₂max, … —
/// to POST /api/import/healthkit/metrics.
///
/// Unlike workouts, daily aggregates don't use anchored queries: every sync
/// re-fetches a trailing window (7 days before the last synced date) and the
/// backend upserts on (metric, date), so late-arriving Watch data
/// self-corrects.  Metric slugs must match the backend's
/// health_metrics_service.KNOWN_METRICS allowlist — unknown slugs are
/// rejected server-side.
@MainActor
final class MetricsSyncEngine {
    static let shared = MetricsSyncEngine()

    private let store = HKHealthStore()
    private let lastSyncKey = "metricsLastSyncDate"
    private let refetchDays = 7
    private let chunkSize = 500
    private var isSyncing = false

    // MARK: - Metric definitions

    private struct QuantityMetric {
        let slug: String
        let identifier: HKQuantityTypeIdentifier
        let options: HKStatisticsOptions
        let unit: HKUnit
        /// Multiplier applied after unit conversion (blood oxygen: fraction → %).
        let scale: Double
    }

    private let quantityMetrics: [QuantityMetric] = [
        .init(slug: "resting_heartrate", identifier: .restingHeartRate,
              options: [.discreteAverage, .discreteMin, .discreteMax],
              unit: HKUnit(from: "count/min"), scale: 1),
        .init(slug: "hrv_sdnn", identifier: .heartRateVariabilitySDNN,
              options: [.discreteAverage, .discreteMin, .discreteMax],
              unit: .secondUnit(with: .milli), scale: 1),
        .init(slug: "vo2max", identifier: .vo2Max,
              options: [.discreteAverage],
              unit: HKUnit(from: "ml/kg*min"), scale: 1),
        .init(slug: "respiratory_rate", identifier: .respiratoryRate,
              options: [.discreteAverage, .discreteMin, .discreteMax],
              unit: HKUnit(from: "count/min"), scale: 1),
        .init(slug: "blood_oxygen", identifier: .oxygenSaturation,
              options: [.discreteAverage, .discreteMin, .discreteMax],
              unit: .percent(), scale: 100),
        .init(slug: "steps", identifier: .stepCount,
              options: [.cumulativeSum], unit: .count(), scale: 1),
        .init(slug: "active_energy", identifier: .activeEnergyBurned,
              options: [.cumulativeSum], unit: .kilocalorie(), scale: 1),
        .init(slug: "body_mass", identifier: .bodyMass,
              options: [.discreteAverage], unit: .gramUnit(with: .kilo), scale: 1),
    ]

    // MARK: - Public

    /// Fetch + upload all daily metrics since the last sync (with a 7-day
    /// re-fetch overlap).  `force`/`since` mirror SyncEngine.performSync so
    /// the full-backfill path covers metrics too.
    func sync(force: Bool = false, since overrideSince: Date? = nil) async {
        guard !isSyncing, HKHealthStore.isHealthDataAvailable() else { return }
        isSyncing = true
        defer { isSyncing = false }

        let cal = Calendar.current
        let now = Date()
        let start: Date
        if let overrideSince {
            start = overrideSince
        } else if !force,
                  let last = UserDefaults.standard.object(forKey: lastSyncKey) as? Date {
            start = cal.date(byAdding: .day, value: -refetchDays, to: last)!
        } else {
            start = cal.date(byAdding: .day, value: -Config.initialSyncDays, to: now)!
        }
        let windowStart = cal.startOfDay(for: start)

        var samples: [MetricSample] = []
        for m in quantityMetrics {
            do {
                samples += try await fetchDaily(m, from: windowStart, to: now)
            } catch {
                print("[MetricsSync] \(m.slug) fetch failed: \(error)")
            }
        }
        do {
            samples += try await fetchSleep(from: windowStart, to: now)
        } catch {
            print("[MetricsSync] sleep fetch failed: \(error)")
        }

        guard !samples.isEmpty else {
            UserDefaults.standard.set(now, forKey: lastSyncKey)
            return
        }

        // Only advance lastSync when every chunk landed — the next run
        // re-fetches the same window and the backend upsert makes it safe.
        var allOK = true
        for chunkStart in stride(from: 0, to: samples.count, by: chunkSize) {
            let end = min(chunkStart + chunkSize, samples.count)
            do {
                try await postChunk(Array(samples[chunkStart..<end]))
            } catch {
                allOK = false
                print("[MetricsSync] upload failed: \(error)")
            }
        }
        if allOK {
            UserDefaults.standard.set(now, forKey: lastSyncKey)
            print("[MetricsSync] uploaded \(samples.count) daily samples")
        }
    }

    /// Reset so the next sync re-fetches the full initial window.
    func resetProgress() {
        UserDefaults.standard.removeObject(forKey: lastSyncKey)
    }

    // MARK: - Quantity metrics (daily statistics buckets)

    private func fetchDaily(
        _ m: QuantityMetric, from start: Date, to end: Date
    ) async throws -> [MetricSample] {
        guard let qtype = HKQuantityType.quantityType(forIdentifier: m.identifier) else {
            return []
        }
        let predicate = HKQuery.predicateForSamples(
            withStart: start, end: end, options: .strictStartDate)

        return try await withCheckedThrowingContinuation { cont in
            let query = HKStatisticsCollectionQuery(
                quantityType: qtype,
                quantitySamplePredicate: predicate,
                options: m.options,
                anchorDate: Calendar.current.startOfDay(for: start),
                intervalComponents: DateComponents(day: 1)
            )
            query.initialResultsHandler = { _, collection, error in
                if let error { cont.resume(throwing: error); return }
                var out: [MetricSample] = []
                collection?.enumerateStatistics(from: start, to: end) { stat, _ in
                    let value: Double? = m.options.contains(.cumulativeSum)
                        ? stat.sumQuantity()?.doubleValue(for: m.unit)
                        : stat.averageQuantity()?.doubleValue(for: m.unit)
                    guard let v = value, v.isFinite, v >= 0 else { return }
                    out.append(MetricSample(
                        metric: m.slug,
                        date: dayKey(stat.startDate),
                        value: v * m.scale,
                        min: stat.minimumQuantity().map { $0.doubleValue(for: m.unit) * m.scale },
                        max: stat.maximumQuantity().map { $0.doubleValue(for: m.unit) * m.scale }
                    ))
                }
                cont.resume(returning: out)
            }
            store.execute(query)
        }
    }

    // MARK: - Sleep (category samples → nightly totals)

    private func fetchSleep(from start: Date, to end: Date) async throws -> [MetricSample] {
        guard let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) else {
            return []
        }
        // No strictStartDate: a session that started before the window but
        // ended inside it still belongs to a night we're syncing.
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: [])

        let samples: [HKCategorySample] = try await withCheckedThrowingContinuation { cont in
            let q = HKSampleQuery(
                sampleType: sleepType, predicate: predicate,
                limit: HKObjectQueryNoLimit, sortDescriptors: nil
            ) { _, s, err in
                if let err { cont.resume(throwing: err); return }
                cont.resume(returning: (s as? [HKCategorySample]) ?? [])
            }
            store.execute(q)
        }

        let asleepValues: Set<Int>
        if #available(iOS 16.0, *) {
            asleepValues = Set(HKCategoryValueSleepAnalysis.allAsleepValues.map(\.rawValue))
        } else {
            asleepValues = [HKCategoryValueSleepAnalysis.asleep.rawValue]
        }
        let inBedValue = HKCategoryValueSleepAnalysis.inBed.rawValue

        var asleep: [(Date, Date)] = []
        var inBed: [(Date, Date)] = []
        for s in samples where s.endDate > s.startDate {
            if asleepValues.contains(s.value) {
                asleep.append((s.startDate, s.endDate))
            } else if s.value == inBedValue {
                inBed.append((s.startDate, s.endDate))
            }
        }

        var out: [MetricSample] = []
        for (day, hours) in nightlyHours(asleep) {
            out.append(MetricSample(metric: "sleep_asleep", date: day, value: hours, min: nil, max: nil))
        }
        for (day, hours) in nightlyHours(inBed) {
            out.append(MetricSample(metric: "sleep_in_bed", date: day, value: hours, min: nil, max: nil))
        }
        return out
    }

    // MARK: - Upload

    private func postChunk(_ samples: [MetricSample]) async throws {
        guard let url = URL(string: "\(Config.backendURL)/api/import/healthkit/metrics") else {
            return
        }
        var req = AuthService.shared.authorizedRequest(url: url, method: "POST", timeout: 60)
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(MetricsBody(metrics: samples))

        let (_, response) = try await URLSession.shared.data(for: req)
        if let http = response as? HTTPURLResponse, http.statusCode >= 400 {
            throw URLError(.badServerResponse)
        }
    }
}

// MARK: - Nonisolated helpers (called from HK query callbacks)

/// Backend stores user-local days.
private func dayKey(_ d: Date) -> String {
    let f = DateFormatter()
    f.dateFormat = "yyyy-MM-dd"
    f.timeZone = .current
    return f.string(from: d)
}

/// Merge overlapping intervals (iPhone + Watch both record sleep — a plain
/// sum would double-count), then total hours per calendar day.  A session is
/// attributed to the day it ENDS: last night's sleep counts toward the
/// morning you woke up.
private func nightlyHours(_ intervals: [(Date, Date)]) -> [String: Double] {
    let sorted = intervals.sorted { $0.0 < $1.0 }
    var merged: [(Date, Date)] = []
    for iv in sorted {
        if let last = merged.last, iv.0 <= last.1 {
            merged[merged.count - 1].1 = max(last.1, iv.1)
        } else {
            merged.append(iv)
        }
    }
    var byDay: [String: Double] = [:]
    for (s, e) in merged {
        byDay[dayKey(e), default: 0] += e.timeIntervalSince(s) / 3600
    }
    return byDay.mapValues { ($0 * 100).rounded() / 100 }
}

// MARK: - Payload models (match backend HKMetricSyncRequest)

private struct MetricSample: Codable {
    let metric: String
    let date:   String
    let value:  Double
    let min:    Double?
    let max:    Double?
}

private struct MetricsBody: Codable {
    let metrics: [MetricSample]
}
