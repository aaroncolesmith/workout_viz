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
    ]

    var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    func requestAuthorization() async throws {
        guard isAvailable else { return }
        try await store.requestAuthorization(toShare: [], read: readTypes)
    }

    /// Fetch workouts modified after `anchor` date.
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
        let predicate = HKQuery.predicateForSamples(
            withStart: workout.startDate, end: workout.endDate, options: .strictStartDate)
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
