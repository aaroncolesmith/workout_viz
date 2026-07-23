"""
Grain-agnostic splits (the 0.1-mi rollup removal).

compute_splits now buckets at 0.05 mi, and rolling_fastest_segments derives
grain from the rows — legacy 0.1-mi splits and new finer splits both work.
"""
from backend.services.splits_service import (
    BUCKET_MILES, METERS_PER_MILE, StreamBundle,
    compute_splits, rolling_fastest_segments,
)


def _uniform_splits(grain: float, total_miles: float, pace_min_mi: float):
    """Synthetic splits at a fixed grain and constant pace."""
    n = int(round(total_miles / grain))
    return [{
        "split_number": b,
        "time_seconds": pace_min_mi * 60 * grain,
        "total_distance_miles": round(b * grain, 3),
        "avg_heartrate": 150.0,
        "elevation_gain_meters": 1.0,
    } for b in range(1, n + 1)]


def test_compute_splits_at_new_grain():
    # 1 mile at exactly 8:00/mi, one sample every ~0.01 mi
    n = 100
    per_sample = 480.0 / n
    bundle = StreamBundle(
        time=[i * per_sample for i in range(1, n + 1)],
        distance=[i * METERS_PER_MILE / n for i in range(1, n + 1)],
    )
    splits = compute_splits(bundle, activity_id=1, activity_name="t", date_str="2026-07-11")
    assert len(splits) == int(round(1.0 / BUCKET_MILES))
    assert BUCKET_MILES == 0.05
    # Sub-second precision preserved (float, not int-rounded), and boundary
    # samples land in the bucket they complete — total time is exact.
    assert abs(sum(s["time_seconds"] for s in splits) - 480.0) < 0.1
    assert splits[0]["total_distance_miles"] == BUCKET_MILES


def test_rolling_segments_same_result_any_grain():
    # Constant 8:00/mi over 2 miles → best 1 mile = 480 s at either grain
    for grain in (0.1, 0.05):
        segs = rolling_fastest_segments(
            _uniform_splits(grain, 2.0, 8.0), [(1.0, "1 Mile")])
        assert len(segs) == 1
        assert abs(segs[0]["time_seconds"] - 480.0) < 0.5, f"grain={grain}"
        assert segs[0]["avg_heartrate"] == 150.0


def test_rolling_segments_finds_fast_stretch():
    # 3 miles: middle mile at 6:00, rest at 9:00 (0.05 grain)
    splits = _uniform_splits(0.05, 3.0, 9.0)
    for s in splits:
        if 1.0 < s["total_distance_miles"] <= 2.0:
            s["time_seconds"] = 6.0 * 60 * 0.05
    segs = rolling_fastest_segments(splits, [(1.0, "1 Mile")])
    assert abs(segs[0]["time_seconds"] - 360.0) < 1.0
    assert segs[0]["start_mile"] == 1.0
    assert segs[0]["end_mile"] == 2.0


def test_rolling_segments_gap_does_not_compress_distance():
    # GPS dropout: splits jump from mile 0.5 to mile 0.95.  The splitter
    # carries the gap's elapsed time into the next populated bucket (anchor
    # delta), so model that: the 0.95 split holds 0.45 mi worth of time.
    splits = [s for s in _uniform_splits(0.05, 1.5, 8.0)
              if not (0.5 < s["total_distance_miles"] < 0.95)]
    gap_split = next(s for s in splits if s["total_distance_miles"] == 0.95)
    gap_split["time_seconds"] = 8.0 * 60 * 0.45
    segs = rolling_fastest_segments(splits, [(1.0, "1 Mile")])
    assert len(segs) == 1
    assert segs[0]["end_mile"] - segs[0]["start_mile"] >= 1.0
    # Scaled time is still ~8:00/mi because pace is uniform
    assert abs(segs[0]["time_seconds"] - 480.0) < 2.0


def test_compute_splits_rescales_noisy_gps_distance_to_reported_total():
    # A real HealthKit route: raw point-to-point Haversine distance always
    # overshoots true distance (GPS jitter never nets out), so a 5.00-mi run
    # at an even 9:15/mi (555 s/mi) might sum to ~5.4 raw "miles" if left
    # unscaled. Unscaled, buckets fill up early and the tail of the workout
    # (samples past raw-mile 5.0) gets dropped entirely — pace reads fast.
    true_total_miles = 5.0
    true_pace_sec_per_mi = 555.0
    true_duration = true_total_miles * true_pace_sec_per_mi
    noise_factor = 1.08  # raw stream overshoots true distance by 8%

    n = 1000
    bundle = StreamBundle(
        time=[i * true_duration / n for i in range(1, n + 1)],
        distance=[i * (true_total_miles * noise_factor) * METERS_PER_MILE / n
                  for i in range(1, n + 1)],
    )
    splits = compute_splits(
        bundle, activity_id=1, activity_name="t", date_str="2026-07-22",
        total_distance_miles=true_total_miles,
    )

    # The full duration is captured — nothing dropped past max_bucket.
    total_time = sum(s["time_seconds"] for s in splits)
    assert abs(total_time - true_duration) < 1.0

    # Every bucket reflects the true pace, not the noise-inflated one.
    for s in splits:
        bucket_pace = s["time_seconds"] / BUCKET_MILES
        assert abs(bucket_pace - true_pace_sec_per_mi) < 1.0


def test_rolling_segments_skips_unreachable_targets():
    segs = rolling_fastest_segments(
        _uniform_splits(0.05, 2.0, 8.0), [(1.0, "1 Mile"), (3.107, "5K")])
    assert [s["label"] for s in segs] == ["1 Mile"]
