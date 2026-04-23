import Foundation
import HealthKit

/// Reads workouts and heart rate from HealthKit.
final class HealthKitManager {
    static let shared = HealthKitManager()
    private let store = HKHealthStore()

    // Types we request read access for
    private let readTypes: Set<HKObjectType> = [
        HKObjectType.workoutType(),
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
}
