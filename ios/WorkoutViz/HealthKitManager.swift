import Foundation
import HealthKit
import CoreLocation

/// Reads workouts and heart rate from HealthKit.
final class HealthKitManager {
    static let shared = HealthKitManager()
    private let store = HKHealthStore()

    // Types we request read access for
    private let readTypes: Set<HKObjectType> = [
        HKObjectType.workoutType(),
        HKSeriesType.workoutRoute(),
        HKObjectType.quantityType(forIdentifier: .heartRate)!,
        HKObjectType.quantityType(forIdentifier: .distanceWalkingRunning)!,
        HKObjectType.quantityType(forIdentifier: .distanceCycling)!,
        HKObjectType.quantityType(forIdentifier: .activeEnergyBurned)!,
        // Daily health metrics (BIO-3) — synced by MetricsSyncEngine
        HKObjectType.quantityType(forIdentifier: .restingHeartRate)!,
        HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN)!,
        HKObjectType.quantityType(forIdentifier: .vo2Max)!,
        HKObjectType.quantityType(forIdentifier: .respiratoryRate)!,
        HKObjectType.quantityType(forIdentifier: .oxygenSaturation)!,
        HKObjectType.quantityType(forIdentifier: .stepCount)!,
        HKObjectType.quantityType(forIdentifier: .bodyMass)!,
        HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!,
    ]

    var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    func requestAuthorization() async throws {
        guard isAvailable else { return }
        try await store.requestAuthorization(toShare: [], read: readTypes)
    }

    /// Result type for anchored HealthKit queries.
    struct AnchoredResult {
        let workouts: [HKWorkout]
        let deletedUUIDs: [UUID]
        let anchor: HKQueryAnchor
    }

    /// Anchored incremental fetch — returns new/updated workouts, deleted workout
    /// UUIDs, and a new anchor to persist for the next call.
    ///
    /// Pass `anchor: nil` for the initial sync (returns everything matching `predicate`).
    /// Pass the saved anchor for incremental syncs (predicate can be nil — all changes
    /// since the anchor are returned regardless of date).
    func fetchWorkoutsAnchored(
        anchor: HKQueryAnchor?,
        predicate: NSPredicate?
    ) async throws -> AnchoredResult {
        return try await withCheckedThrowingContinuation { cont in
            let query = HKAnchoredObjectQuery(
                type: .workoutType(),
                predicate: predicate,
                anchor: anchor,
                limit: HKObjectQueryNoLimit
            ) { _, samples, deletedObjects, newAnchor, error in
                if let error { cont.resume(throwing: error); return }
                guard let newAnchor else {
                    cont.resume(throwing: URLError(.unknown)); return
                }
                let workouts = (samples as? [HKWorkout]) ?? []
                let deleted  = (deletedObjects ?? []).map { $0.uuid }
                cont.resume(returning: AnchoredResult(
                    workouts: workouts, deletedUUIDs: deleted, anchor: newAnchor
                ))
            }
            store.execute(query)
        }
    }

    /// Register an observer query so HealthKit wakes the app when new workouts are
    /// saved.  Requires `UIBackgroundModes: ["healthkit"]` in Info.plist — enable
    /// the "Background Delivery" option in Xcode's HealthKit capability settings.
    func registerWorkoutObserver(onUpdate: @escaping () -> Void) {
        store.enableBackgroundDelivery(for: .workoutType(), frequency: .immediate) { ok, err in
            if !ok { print("[HK] enableBackgroundDelivery failed: \(err?.localizedDescription ?? "?")") }
        }
        let q = HKObserverQuery(sampleType: .workoutType(), predicate: nil) { _, done, error in
            if error == nil { onUpdate() }
            done()
        }
        store.execute(q)
    }

    /// Wake the app when new sleep data lands (typically right after the user
    /// wakes up and the Watch syncs) — drives the morning readiness report.
    func registerSleepObserver(onUpdate: @escaping () -> Void) {
        guard let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) else { return }
        store.enableBackgroundDelivery(for: sleepType, frequency: .immediate) { ok, err in
            if !ok { print("[HK] sleep background delivery failed: \(err?.localizedDescription ?? "?")") }
        }
        let q = HKObserverQuery(sampleType: sleepType, predicate: nil) { _, done, error in
            if error == nil { onUpdate() }
            done()
        }
        store.execute(q)
    }

    /// Legacy date-range fetch — kept for performFullBackfill's predicate path.
    func fetchWorkouts(since startDate: Date) async throws -> [HKWorkout] {
        let predicate = HKQuery.predicateForSamples(
            withStart: startDate, end: Date(), options: .strictStartDate)
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: false)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: HKObjectType.workoutType(),
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [sort]
            ) { _, samples, error in
                if let error { continuation.resume(throwing: error); return }
                continuation.resume(returning: (samples as? [HKWorkout]) ?? [])
            }
            store.execute(query)
        }
    }

    /// Fetch average and max HR for a specific workout.
    func fetchHeartRate(for workout: HKWorkout) async throws -> (avg: Double?, max: Double?) {
        let hrType = HKQuantityType.quantityType(forIdentifier: .heartRate)!
        let predicate = HKQuery.predicateForSamples(
            withStart: workout.startDate, end: workout.endDate, options: .strictStartDate)

        let samples: [HKQuantitySample] = try await withCheckedThrowingContinuation { cont in
            let query = HKSampleQuery(
                sampleType: hrType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: nil
            ) { _, s, err in
                if let err { cont.resume(throwing: err); return }
                cont.resume(returning: (s as? [HKQuantitySample]) ?? [])
            }
            store.execute(query)
        }

        guard !samples.isEmpty else { return (nil, nil) }
        let bpms = samples.map { $0.quantity.doubleValue(for: .init(from: "count/min")) }
        return (bpms.reduce(0, +) / Double(bpms.count), bpms.max())
    }

    /// Fetch per-sample cumulative distance for a workout. Works for treadmill
    /// runs, indoor rides, and outdoor activities that happen to record distance
    /// samples even without GPS routes. Returned pairs are (timestamp, cumulative
    /// meters from workout start).
    func fetchDistanceSeries(for workout: HKWorkout) async throws -> [(Date, Double)] {
        let typeId: HKQuantityTypeIdentifier
        switch workout.workoutActivityType {
        case .cycling:            typeId = .distanceCycling
        case .swimming:           typeId = .distanceSwimming
        default:                  typeId = .distanceWalkingRunning
        }
        guard let qtype = HKQuantityType.quantityType(forIdentifier: typeId) else {
            return []
        }
        // Filter by the workout's source to avoid double-counting samples from
        // both Apple Watch and iPhone during the same workout time window.
        let timePredicate = HKQuery.predicateForSamples(
            withStart: workout.startDate, end: workout.endDate, options: .strictStartDate)
        let sourcePredicate = HKQuery.predicateForObjects(
            from: Set([workout.sourceRevision.source]))
        let predicate = NSCompoundPredicate(andPredicateWithSubpredicates: [
            timePredicate, sourcePredicate
        ])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        let samples: [HKQuantitySample] = try await withCheckedThrowingContinuation { cont in
            let query = HKSampleQuery(
                sampleType: qtype, predicate: predicate,
                limit: HKObjectQueryNoLimit, sortDescriptors: [sort]
            ) { _, s, err in
                if let err { cont.resume(throwing: err); return }
                cont.resume(returning: (s as? [HKQuantitySample]) ?? [])
            }
            store.execute(query)
        }
        // Each sample carries a delta-distance. Accumulate to cumulative meters,
        // using the sample's endDate as the timestamp anchor.
        var cumulative = 0.0
        var out: [(Date, Double)] = []
        for s in samples {
            cumulative += s.quantity.doubleValue(for: .meter())
            out.append((s.endDate, cumulative))
        }
        return out
    }

    /// Fetch the full per-sample HR series for a workout. Each tuple is (timestamp, bpm).
    func fetchHeartRateSeries(for workout: HKWorkout) async throws -> [(Date, Double)] {
        let hrType = HKQuantityType.quantityType(forIdentifier: .heartRate)!
        let predicate = HKQuery.predicateForSamples(
            withStart: workout.startDate, end: workout.endDate, options: .strictStartDate)
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        let samples: [HKQuantitySample] = try await withCheckedThrowingContinuation { cont in
            let query = HKSampleQuery(
                sampleType: hrType, predicate: predicate,
                limit: HKObjectQueryNoLimit, sortDescriptors: [sort]
            ) { _, s, err in
                if let err { cont.resume(throwing: err); return }
                cont.resume(returning: (s as? [HKQuantitySample]) ?? [])
            }
            store.execute(query)
        }
        let bpmUnit = HKUnit(from: "count/min")
        return samples.map { ($0.startDate, $0.quantity.doubleValue(for: bpmUnit)) }
    }

    /// True when the user has granted permission to read workout routes.
    /// Apple's HKHealthStore only returns notDetermined/sharingAuthorized/sharingDenied
    /// for *write* auth — for read we infer from whether any route samples are
    /// ever returned. See `fetchRoute` for empty-route handling.
    var routeAuthStatus: HKAuthorizationStatus {
        store.authorizationStatus(for: HKSeriesType.workoutRoute())
    }

    /// Fetch the full GPS route for a workout as a sorted list of CLLocations.
    /// Returns [] when the workout has no route samples (strength, indoor, etc).
    func fetchRoute(for workout: HKWorkout) async throws -> [CLLocation] {
        // 1. Find the route object(s) associated with this workout.
        let routePredicate = HKQuery.predicateForObjects(from: workout)
        let routeSamples: [HKWorkoutRoute] = try await withCheckedThrowingContinuation { cont in
            let q = HKSampleQuery(
                sampleType: HKSeriesType.workoutRoute(), predicate: routePredicate,
                limit: HKObjectQueryNoLimit, sortDescriptors: nil
            ) { _, s, err in
                if let err { cont.resume(throwing: err); return }
                cont.resume(returning: (s as? [HKWorkoutRoute]) ?? [])
            }
            store.execute(q)
        }
        guard !routeSamples.isEmpty else { return [] }

        // 2. For each route, stream its CLLocations. HKWorkoutRouteQuery's result
        //    handler fires repeatedly until `done == true`.
        var all: [CLLocation] = []
        for route in routeSamples {
            let locs: [CLLocation] = try await withCheckedThrowingContinuation { cont in
                var acc: [CLLocation] = []
                let q = HKWorkoutRouteQuery(route: route) { _, batch, done, err in
                    if let err { cont.resume(throwing: err); return }
                    if let batch { acc.append(contentsOf: batch) }
                    if done { cont.resume(returning: acc) }
                }
                store.execute(q)
            }
            all.append(contentsOf: locs)
        }
        return all.sorted { $0.timestamp < $1.timestamp }
    }
}

// MARK: - HKWorkout helpers

extension HKWorkoutActivityType {
    /// Maps HealthKit workout types to our backend type strings.
    var backendType: String {
        switch self {
        case .running:                     return "Run"
        case .cycling:                     return "Ride"
        case .walking:                     return "Walk"
        case .hiking:                      return "Hike"
        case .swimming:                    return "Swim"
        case .traditionalStrengthTraining: return "WeightTraining"
        case .functionalStrengthTraining:  return "FunctionalStrengthTraining"
        case .highIntensityIntervalTraining: return "HIIT"
        case .coreTraining:                return "CoreTraining"
        case .yoga:                        return "Yoga"
        case .pilates:                     return "Pilates"
        case .mindAndBody:                 return "MindAndBody"
        case .crossTraining:               return "Crossfit"
        case .elliptical:                  return "Elliptical"
        case .stairClimbing:               return "StairStepper"
        case .rowing:                      return "Rowing"
        case .cooldown:                    return "Cooldown"
        default:                           return "Workout"
        }
    }

    /// Which workout types are expected to have GPS route data worth fetching.
    var isGPS: Bool {
        switch self {
        case .running, .cycling, .walking, .hiking, .swimming:
            return true
        default:
            return false
        }
    }
}
