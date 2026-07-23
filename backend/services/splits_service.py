"""
splits_service.py — Source-agnostic split computation.

Takes a standardized stream bundle (time + cumulative distance + optional
heartrate / cadence / velocity / altitude arrays, all indexed identically)
and buckets it into fixed-distance splits.

Adapters convert Strava's `streams` dict or HealthKit's (locations, hr)
timeseries into the standardized shape. Both then call the same splitter,
so there is exactly one implementation of the bucketing math.

Grain: new imports bucket at BUCKET_MILES (0.05 mi ≈ 80 m — fine enough for
sharp fastest-segment windows, coarse enough that each bucket still holds
several GPS/HR samples).  Historical rows in the splits table may be the
legacy 0.1-mi grain; consumers must NOT assume a grain — use
`rolling_fastest_segments`, which derives everything from the rows.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


METERS_PER_MILE = 1609.344
BUCKET_MILES = 0.05


@dataclass
class StreamBundle:
    """Normalized per-sample streams, all lists share the same index."""
    time:      List[float]                    # seconds since workout start
    distance:  List[float]                    # cumulative meters
    heartrate: Optional[List[float]] = None
    cadence:   Optional[List[float]] = None
    velocity:  Optional[List[float]] = None
    altitude:  Optional[List[float]] = None


# ── Public: compute splits from a normalized StreamBundle ────────────────────

def compute_splits(
    bundle: StreamBundle,
    activity_id: int,
    activity_name: str,
    date_str: str,
    total_distance_miles: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Bucket a stream bundle into BUCKET_MILES splits.

    Returns a list of dicts matching the `splits` table schema used by the
    rest of the app (the same shape that Strava sync produces).
    """
    n = len(bundle.distance)
    if n == 0 or len(bundle.time) != n:
        return []

    # Convert cumulative distance to miles and assign a 1-indexed bucket.
    miles = [d / METERS_PER_MILE for d in bundle.distance]
    if total_distance_miles is None:
        total_distance_miles = miles[-1]
    elif miles[-1] > 0:
        # Raw point-to-point stream distance (esp. Haversine-summed GPS,
        # which never nets out jitter) routinely drifts from the activity's
        # authoritative reported total. Anchor every bucket boundary to that
        # known-accurate total instead of the noisy stream's own sum —
        # otherwise buckets fill up "early" and every pace reads too fast,
        # with the tail of the workout silently dropped past max_bucket.
        scale = total_distance_miles / miles[-1]
        miles = [m * scale for m in miles]

    max_bucket = max(1, int(total_distance_miles / BUCKET_MILES))
    if max_bucket == 0:
        return []

    # Group sample indexes by bucket number (1-indexed).  A sample exactly on
    # a boundary belongs to the bucket it COMPLETES (m in (g·(b−1), g·b] → b),
    # otherwise the final sample of every workout falls into a bucket past
    # max_bucket and its time silently vanishes.
    buckets: Dict[int, List[int]] = {}
    for i, m in enumerate(miles):
        b = int(math.ceil(m / BUCKET_MILES - 1e-9))
        if 1 <= b <= max_bucket:
            buckets.setdefault(b, []).append(i)

    splits: List[Dict[str, Any]] = []
    prev_bucket_max_time: Optional[float] = None

    for b in range(1, max_bucket + 1):
        idxs = buckets.get(b, [])
        if not idxs:
            # Bucket gap (e.g. GPS dropout); skip but keep prev_bucket_max_time
            # unchanged so the next populated bucket gets a correct delta.
            continue

        times = [bundle.time[i] for i in idxs]
        bucket_end = max(times)

        # Time spent in this bucket = end-of-this - end-of-prev. For bucket 1
        # the prior anchor is the workout start (t=0) — which also correctly
        # handles low-density streams where the first bucket has a single sample.
        anchor = prev_bucket_max_time if prev_bucket_max_time is not None else 0.0
        time_secs = bucket_end - anchor
        prev_bucket_max_time = bucket_end

        def _mean(arr: Optional[List[float]]) -> Optional[float]:
            if not arr: return None
            vals = [arr[i] for i in idxs if arr[i] is not None]
            return sum(vals) / len(vals) if vals else None

        def _max(arr: Optional[List[float]]) -> Optional[float]:
            if not arr: return None
            vals = [arr[i] for i in idxs if arr[i] is not None]
            return max(vals) if vals else None

        elev_gain = 0.0
        if bundle.altitude:
            alts = [bundle.altitude[i] for i in idxs if bundle.altitude[i] is not None]
            if alts:
                elev_gain = max(0.0, max(alts) - min(alts))

        # Sub-second precision matters at fine grain: a 0.05-mi bucket takes
        # ~24 s at 8 min/mi, so int-rounding every bucket would accumulate
        # real error over a marathon of windows.
        time_secs = max(0.0, round(time_secs, 2))
        time_int = int(round(time_secs))
        splits.append({
            '0.1_mile':              b,
            'split_number':          b,
            'time_seconds':          time_secs,
            'time_minutes':          f"{time_int // 60:02d}:{time_int % 60:02d}",
            'max_heartrate':         _max(bundle.heartrate),
            'avg_heartrate':         _mean(bundle.heartrate),
            'avg_cadence':           _mean(bundle.cadence),
            'avg_velocity':          _mean(bundle.velocity),
            'elevation_gain_meters': elev_gain,
            'activity_id':           activity_id,
            'activity_name':         activity_name,
            'total_distance_miles':  round(b * BUCKET_MILES, 3),
            'date':                  date_str,
            'id':                    activity_id,
        })

    return splits


# ── Grain-agnostic rolling fastest segments ──────────────────────────────────

def rolling_fastest_segments(
    splits: List[Dict[str, Any]],
    targets: List[tuple],
) -> List[Dict[str, Any]]:
    """
    Fastest rolling window per target distance, over splits of ANY grain —
    legacy 0.1-mi rows and new BUCKET_MILES rows are handled identically
    because everything derives from the rows' own cumulative distances.

    Two-pointer over cumulative (distance, time): each window is the
    tightest run of consecutive splits covering ≥ target miles, so a GPS
    dropout (missing bucket) widens the recorded distance rather than
    silently compressing a "1 mile" into 0.9.  The window's time is scaled
    to the exact target (time × target/actual) — pace-preserving, and
    strictly less quantization error than the old fixed-bucket-count sum.

    targets: [(miles, label), …].  Returns one dict per achievable target:
      {distance_miles, label, time_seconds, start_mile, end_mile,
       avg_heartrate, elevation_gain_meters}
    """
    rows = sorted(splits, key=lambda s: float(s.get("split_number") or 0))
    if not rows:
        return []

    n = len(rows)
    # Prefix arrays: d[k] / t[k] = cumulative miles / seconds after k splits.
    d = [0.0] * (n + 1)
    t = [0.0] * (n + 1)
    for k, r in enumerate(rows):
        d[k + 1] = float(r.get("total_distance_miles") or 0)
        t[k + 1] = t[k] + float(r.get("time_seconds") or 0)
    total_dist = d[n]

    results = []
    for target_miles, label in targets:
        if total_dist < target_miles * 0.95:
            continue

        best = None       # (scaled_time, a, b)
        a = 0
        for b in range(1, n + 1):
            # Largest window start a with d[b] - d[a] >= target (a only moves right).
            while a + 1 <= b and d[b] - d[a + 1] >= target_miles:
                a += 1
            span = d[b] - d[a]
            if span < target_miles:
                continue
            scaled = (t[b] - t[a]) * (target_miles / span)
            if best is None or scaled < best[0]:
                best = (scaled, a, b)

        if best is None:
            continue
        scaled_time, a, b = best
        window = rows[a:b]
        hrs = [float(r["avg_heartrate"]) for r in window if r.get("avg_heartrate")]
        results.append({
            "distance_miles":        target_miles,
            "label":                 label,
            "time_seconds":          round(scaled_time, 1),
            "start_mile":            round(d[a], 2),
            "end_mile":              round(d[b], 2),
            "avg_heartrate":         round(sum(hrs) / len(hrs), 1) if hrs else None,
            "elevation_gain_meters": round(sum(float(r.get("elevation_gain_meters") or 0)
                                              for r in window), 2),
        })

    return results


# ── Adapter: Strava streams → StreamBundle ───────────────────────────────────

def from_strava_streams(streams: Dict[str, Any]) -> StreamBundle:
    """
    Convert a stravalib `streams` dict (each value has a `.data` list) into
    a normalized StreamBundle.
    """
    def _data(key: str) -> Optional[List[float]]:
        s = streams.get(key)
        if s is None:
            return None
        return list(s.data) if hasattr(s, 'data') else list(s)

    time_arr = _data('time') or []
    dist_arr = _data('distance') or []
    return StreamBundle(
        time      = time_arr,
        distance  = dist_arr,
        heartrate = _data('heartrate'),
        cadence   = _data('cadence'),
        velocity  = _data('velocity_smooth'),
        altitude  = _data('altitude'),
    )


# ── Adapter: HealthKit route + HR series → StreamBundle ──────────────────────

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters between two lat/lng points."""
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def from_distance_stream(
    distance_samples: List[Dict[str, float]],
    heartrate: Optional[List[Dict[str, float]]] = None,
) -> StreamBundle:
    """
    Indoor-workout adapter: build a StreamBundle from (t, cumulative meters)
    samples (e.g. treadmill `distanceWalkingRunning` from Apple Watch).
    No GPS, no altitude — just time + distance + optional HR.
    """
    if not distance_samples:
        return StreamBundle(time=[], distance=[])

    samples = sorted(distance_samples, key=lambda s: s['t'])
    time_arr = [float(s['t']) for s in samples]
    dist_arr = [float(s['m']) for s in samples]

    hr_arr: Optional[List[float]] = None
    if heartrate:
        hr_sorted = sorted(heartrate, key=lambda s: s['t'])
        hr_times  = [s['t'] for s in hr_sorted]
        hr_vals   = [s['bpm'] for s in hr_sorted]
        hr_arr = []
        j = 0
        for t in time_arr:
            while j + 1 < len(hr_times) and abs(hr_times[j + 1] - t) < abs(hr_times[j] - t):
                j += 1
            hr_arr.append(hr_vals[j])

    return StreamBundle(time=time_arr, distance=dist_arr, heartrate=hr_arr)


def from_healthkit_streams(
    locations: List[Dict[str, float]],
    heartrate: Optional[List[Dict[str, float]]] = None,
) -> StreamBundle:
    """
    Convert a HealthKit-style `(locations, heartrate)` payload into a
    normalized StreamBundle.

    `locations`: list of {t, lat, lng, alt} dicts, t = seconds since start
    `heartrate`: list of {t, bpm} dicts, t = seconds since start

    Distance is computed via Haversine between consecutive locations.
    HR is resampled onto the location timeline via nearest-timestamp match.
    """
    if not locations:
        return StreamBundle(time=[], distance=[])

    # Time + cumulative distance from locations.
    time_arr: List[float] = []
    dist_arr: List[float] = []
    alt_arr:  List[float] = []
    cum = 0.0
    prev = None
    for loc in locations:
        if prev is not None:
            cum += _haversine_m(prev['lat'], prev['lng'], loc['lat'], loc['lng'])
        time_arr.append(float(loc.get('t', 0.0)))
        dist_arr.append(cum)
        alt_arr.append(float(loc.get('alt', 0.0)))
        prev = loc

    # Resample HR onto the location timeline — nearest-timestamp match.
    hr_arr: Optional[List[float]] = None
    if heartrate:
        hr_sorted = sorted(heartrate, key=lambda s: s['t'])
        hr_times  = [s['t'] for s in hr_sorted]
        hr_vals   = [s['bpm'] for s in hr_sorted]
        hr_arr = []
        j = 0
        for t in time_arr:
            # advance j to the HR sample closest to t
            while j + 1 < len(hr_times) and abs(hr_times[j + 1] - t) < abs(hr_times[j] - t):
                j += 1
            hr_arr.append(hr_vals[j])

    return StreamBundle(
        time      = time_arr,
        distance  = dist_arr,
        heartrate = hr_arr,
        altitude  = alt_arr or None,
    )
