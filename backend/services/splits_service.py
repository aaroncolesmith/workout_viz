"""
splits_service.py — Source-agnostic 0.1-mile split computation.

Takes a standardized stream bundle (time + cumulative distance + optional
heartrate / cadence / velocity / altitude arrays, all indexed identically)
and buckets it into 0.1-mile splits matching the shape that Strava-sourced
activities already produce.

Adapters convert Strava's `streams` dict or HealthKit's (locations, hr)
timeseries into the standardized shape. Both then call the same splitter,
so there is exactly one implementation of the bucketing math.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


METERS_PER_MILE = 1609.344
BUCKET_MILES = 0.1


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
    Bucket a stream bundle into 0.1-mile splits.

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

    max_bucket = max(1, int(total_distance_miles / BUCKET_MILES))
    if max_bucket == 0:
        return []

    # Group sample indexes by bucket number (1-indexed).
    buckets: Dict[int, List[int]] = {}
    for i, m in enumerate(miles):
        b = int(m / BUCKET_MILES) + 1
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

        time_int = max(0, int(round(time_secs)))
        splits.append({
            '0.1_mile':              b,
            'split_number':          b,
            'time_seconds':          time_int,
            'time_minutes':          f"{time_int // 60:02d}:{time_int % 60:02d}",
            'max_heartrate':         _max(bundle.heartrate),
            'avg_heartrate':         _mean(bundle.heartrate),
            'avg_cadence':           _mean(bundle.cadence),
            'avg_velocity':          _mean(bundle.velocity),
            'elevation_gain_meters': elev_gain,
            'activity_id':           activity_id,
            'activity_name':         activity_name,
            'total_distance_miles':  round(b * BUCKET_MILES, 1),
            'date':                  date_str,
            'id':                    activity_id,
        })

    return splits


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
