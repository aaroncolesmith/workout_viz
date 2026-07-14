"""
BIO-4 — daily health metrics from the Apple Health XML importer.

Exercises _scan_records/_DailyMetrics on a synthetic export.xml: unit
normalisation, per-source max for cumulative metrics, sleep interval
merging, and that workout HR matching still works in the combined pass.
"""
from backend.services.apple_health_service import _DailyMetrics, _scan_records


def _xml(records: str) -> bytes:
    return f'<?xml version="1.0"?><HealthData>{records}</HealthData>'.encode()


def _record(rtype, value, start, end=None, unit="", source="Apple Watch"):
    end = end or start
    return (f'<Record type="{rtype}" sourceName="{source}" unit="{unit}" '
            f'value="{value}" startDate="{start}" endDate="{end}"/>')


def test_daily_metrics_accumulation_and_normalisation():
    xml = _xml(
        # Two RHR days (avg metric with min/max)
        _record("HKQuantityTypeIdentifierRestingHeartRate", 52, "2026-07-09 08:00:00 -0700")
        + _record("HKQuantityTypeIdentifierRestingHeartRate", 54, "2026-07-10 08:00:00 -0700")
        + _record("HKQuantityTypeIdentifierRestingHeartRate", 50, "2026-07-10 21:00:00 -0700")
        # Oxygen saturation as a fraction → %
        + _record("HKQuantityTypeIdentifierOxygenSaturation", 0.97, "2026-07-10 08:00:00 -0700")
        # Body mass in lb → kg
        + _record("HKQuantityTypeIdentifierBodyMass", 172, "2026-07-10 07:00:00 -0700", unit="lb")
        # Steps from two sources the same day: max source total wins, not the sum
        + _record("HKQuantityTypeIdentifierStepCount", 4000, "2026-07-10 09:00:00 -0700", source="iPhone")
        + _record("HKQuantityTypeIdentifierStepCount", 3000, "2026-07-10 12:00:00 -0700", source="iPhone")
        + _record("HKQuantityTypeIdentifierStepCount", 6500, "2026-07-10 10:00:00 -0700", source="Apple Watch")
        # Unknown record type is ignored
        + _record("HKQuantityTypeIdentifierDietaryWater", 500, "2026-07-10 09:00:00 -0700")
    )
    daily = _DailyMetrics()
    _scan_records(xml, [], daily)
    by_key = {(s["metric"], s["date"]): s for s in daily.samples()}

    rhr = by_key[("resting_heartrate", "2026-07-10")]
    assert rhr["value"] == 52.0            # avg(54, 50)
    assert rhr["min"] == 50 and rhr["max"] == 54
    assert by_key[("resting_heartrate", "2026-07-09")]["value"] == 52.0

    assert by_key[("blood_oxygen", "2026-07-10")]["value"] == 97.0
    assert abs(by_key[("body_mass", "2026-07-10")]["value"] - 78.02) < 0.01
    assert by_key[("steps", "2026-07-10")]["value"] == 7000.0   # iPhone total beats Watch
    assert not any(m == "dietary_water" for m, _ in by_key)


def test_sleep_interval_merge_and_wake_day_attribution():
    xml = _xml(
        # Watch + iPhone overlap 23:00–03:00 / 23:30–06:30 → merged 23:00–06:30 = 7.5h
        _record("HKCategoryTypeIdentifierSleepAnalysis", "HKCategoryValueSleepAnalysisAsleepCore",
                "2026-07-09 23:00:00 -0700", "2026-07-10 03:00:00 -0700")
        + _record("HKCategoryTypeIdentifierSleepAnalysis", "HKCategoryValueSleepAnalysisAsleepDeep",
                  "2026-07-09 23:30:00 -0700", "2026-07-10 06:30:00 -0700", source="iPhone")
        + _record("HKCategoryTypeIdentifierSleepAnalysis", "HKCategoryValueSleepAnalysisInBed",
                  "2026-07-09 22:45:00 -0700", "2026-07-10 06:45:00 -0700")
        # Awake segments are neither asleep nor in-bed
        + _record("HKCategoryTypeIdentifierSleepAnalysis", "HKCategoryValueSleepAnalysisAwake",
                  "2026-07-10 02:00:00 -0700", "2026-07-10 02:10:00 -0700")
    )
    daily = _DailyMetrics()
    _scan_records(xml, [], daily)
    by_key = {(s["metric"], s["date"]): s["value"] for s in daily.samples()}

    # Attributed to the wake-up morning, spanning midnight
    assert by_key[("sleep_asleep", "2026-07-10")] == 7.5
    assert by_key[("sleep_in_bed", "2026-07-10")] == 8.0
    assert ("sleep_asleep", "2026-07-09") not in by_key


def test_hr_matching_still_works_in_combined_pass():
    from datetime import datetime
    start = datetime.fromisoformat("2026-07-10T07:00:00-07:00")
    end = datetime.fromisoformat("2026-07-10T08:00:00-07:00")
    workout = {"start_ts": start.timestamp(), "end_ts": end.timestamp(),
               "hr_sum": 0.0, "hr_count": 0, "hr_max": 0.0}
    xml = _xml(
        _record("HKQuantityTypeIdentifierHeartRate", 150, "2026-07-10 07:10:00 -0700")
        + _record("HKQuantityTypeIdentifierHeartRate", 160, "2026-07-10 07:30:00 -0700")
        + _record("HKQuantityTypeIdentifierHeartRate", 120, "2026-07-10 09:00:00 -0700")  # outside
    )
    daily = _DailyMetrics()
    _scan_records(xml, [workout], daily)
    assert workout["hr_count"] == 2
    assert workout["hr_sum"] == 310.0
    assert workout["hr_max"] == 160.0
