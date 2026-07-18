"""
Import API — Apple Health XML upload + native HealthKit sync (HK-3).

All endpoints are authenticated via JWT (get_current_user).
The shared X-Api-Key / HEALTHKIT_API_KEY path is removed (HK-3).
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.api.deps import get_current_user
from backend.services.apple_health_service import start_import, get_import_status
from backend.services.data_service import get_data_service
from backend.models import schemas
from pydantic import BaseModel

router = APIRouter(prefix="/api/import", tags=["import"])

MAX_UPLOAD_BYTES = 256 * 1024 * 1024  # 256 MB


# ── Apple Health XML upload ───────────────────────────────────────────────────

@router.post("/apple-health", response_model=schemas.ImportStartResponse)
async def upload_apple_health(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """Accept an Apple Health export ZIP/XML and kick off a background import."""
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 256 MB).")
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file.")
    result = start_import(contents, file.filename or "export.zip", user_id=user_id)
    return result


@router.get("/apple-health/status", response_model=schemas.ImportStatusResponse)
def apple_health_status(user_id: str = Depends(get_current_user)):
    """Poll for import progress."""
    return get_import_status(user_id)


# ── HealthKit native sync (iOS companion app) ──────────────────────────────────

class HKLocationSample(BaseModel):
    t:   float
    lat: float
    lng: float
    alt: Optional[float] = None


class HKHeartRateSample(BaseModel):
    t:   float
    bpm: float


class HKDistanceSample(BaseModel):
    t: float
    m: float


class HKStreams(BaseModel):
    locations: List[HKLocationSample] = []
    distance:  List[HKDistanceSample] = []
    heartrate: List[HKHeartRateSample] = []


class HKSwimLap(BaseModel):
    lap_number:       int
    duration_seconds: float
    distance_meters:  Optional[float] = None
    stroke_type:      Optional[str] = None
    stroke_count:     Optional[int] = None
    avg_heartrate:    Optional[float] = None
    is_rest:          bool = False


class HKWorkout(BaseModel):
    source_id:          str
    type:               str
    start_date:         str
    end_date:           str
    duration_sec:       float
    distance_meters:    Optional[float] = None
    active_energy_kcal: Optional[float] = None
    avg_heartrate:      Optional[float] = None
    max_heartrate:      Optional[float] = None
    pool_length_meters: Optional[float] = None
    swim_laps:          List[HKSwimLap] = []
    streams:            Optional[HKStreams] = None


class HKSyncRequest(BaseModel):
    workouts: List[HKWorkout]


class HKAddedActivity(BaseModel):
    id:        int
    source_id: str


class HKSyncResponse(BaseModel):
    added:            int
    skipped:          int
    splits_built:     int = 0
    # Newly inserted activities (id ↔ HK UUID) so the iOS app can fetch the
    # comparison verdict for the just-finished workout and notify (CMP-5).
    added_activities: List[HKAddedActivity] = []


# ── Daily health metrics sync (BIO-2) ──────────────────────────────────────────

class HKMetricSample(BaseModel):
    metric:    str                     # canonical slug, see health_metrics_service.KNOWN_METRICS
    date:      str                     # YYYY-MM-DD, user-local day
    value:     float
    min:       Optional[float] = None
    max:       Optional[float] = None
    source_id: Optional[str] = None


class HKMetricSyncRequest(BaseModel):
    metrics: List[HKMetricSample]


class HKMetricSyncResponse(BaseModel):
    added:           int
    updated:         int
    skipped:         int
    unknown_metrics: List[str] = []


@router.post("/healthkit/metrics", response_model=HKMetricSyncResponse)
def healthkit_metrics_sync(
    body: HKMetricSyncRequest,
    user_id: str = Depends(get_current_user),
):
    """Batched upsert of daily health metrics (resting HR, HRV, sleep, …)."""
    from backend.services import health_metrics_service

    svc = get_data_service(user_id)
    result = health_metrics_service.upsert_metrics(
        svc._conn(), [s.model_dump() for s in body.metrics]
    )
    if result["added"] or result["updated"]:
        svc.get_analytics_cache().flush()
    return result


@router.get("/healthkit/missing-streams")
def healthkit_missing_streams(user_id: str = Depends(get_current_user)):
    """Diagnostic: activities missing splits."""
    svc = get_data_service(user_id)
    conn = svc._conn()
    DIST_TYPES = ('Run', 'Ride', 'Walk', 'Hike', 'Swim', 'VirtualRun', 'TrailRun', 'VirtualRide')
    rows = conn.execute(
        f"""
        SELECT a.id, a.type, a.start_date, a.date, a.distance_miles,
               a.map_polyline IS NOT NULL AS has_polyline
          FROM activities a
          LEFT JOIN splits s ON s.activity_id = a.id
         WHERE a.source = 'apple_health'
           AND a.type IN ({','.join(['?']*len(DIST_TYPES))})
         GROUP BY a.id
        HAVING COUNT(s.id) = 0
         ORDER BY a.start_date DESC
        """,
        DIST_TYPES
    ).fetchall()
    return {"count": len(rows), "activities": [dict(r) for r in rows]}


@router.get("/healthkit/coverage")
def healthkit_coverage(user_id: str = Depends(get_current_user)):
    """
    Diagnostic: total count of Apple-Health-sourced activities on the server.
    The iOS app compares this against its local HealthKit workout count to
    detect gaps (e.g. an interrupted backfill) without requiring the user to
    remember to tap "Backfill HealthKit" themselves.
    """
    svc = get_data_service(user_id)
    conn = svc._conn()
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM activities WHERE source = 'apple_health'"
    ).fetchone()
    return {"count": row["count"]}


@router.post("/healthkit", response_model=HKSyncResponse)
def healthkit_sync(
    body: HKSyncRequest,
    user_id: str = Depends(get_current_user),
):
    """Native iOS HealthKit sync — authenticated via Bearer JWT (HK-3)."""
    import polyline as _polyline
    from datetime import datetime
    from backend.services.apple_health_service import hk_activity_id
    from backend.services.splits_service import (
        from_healthkit_streams, from_distance_stream, compute_splits,
    )

    def _encode_polyline(locations: list, max_points: int = 1500) -> str:
        if not locations:
            return ""
        n = len(locations)
        if n <= max_points:
            pts = [(loc['lat'], loc['lng']) for loc in locations]
        else:
            step = n / max_points
            pts = [(locations[int(i * step)]['lat'], locations[int(i * step)]['lng'])
                   for i in range(max_points)]
            last = locations[-1]
            if pts[-1] != (last['lat'], last['lng']):
                pts.append((last['lat'], last['lng']))
        return _polyline.encode(pts)

    svc = get_data_service(user_id)
    conn = svc._conn()
    added = skipped = splits_built = 0
    added_activities: list = []

    for w in body.workouts:
        if w.duration_sec < 60:
            skipped += 1
            continue

        duration_min = w.duration_sec / 60.0
        distance_m = w.distance_meters or 0.0
        distance_miles = distance_m / 1609.344
        pace = None
        if distance_miles > 0.05 and duration_min > 0:
            pace = duration_min / distance_miles

        try:
            start_dt = datetime.fromisoformat(w.start_date)
            date_str = start_dt.date().isoformat()
            start_date_local = start_dt.isoformat()
        except Exception:
            skipped += 1
            continue

        # No date embedded — the frontend's formatActivityName() appends one
        # consistently everywhere it's displayed; baking it in here just
        # produces doubled dates once that formatting is applied.
        activity_name = w.type
        start_ts = start_dt.timestamp()

        match = conn.execute(
            """SELECT id FROM activities
                WHERE source = 'apple_health'
                  AND type = ?
                  AND ABS(strftime('%s', start_date) - ?) < 60
                LIMIT 1""",
            (w.type, start_ts)
        ).fetchone()

        if match:
            activity_id = match["id"]
            existing = match
        else:
            activity_id = hk_activity_id(w.source_id)
            existing = conn.execute(
                "SELECT id FROM activities WHERE id = ?", (activity_id,)
            ).fetchone()

        if not existing:
            conn.execute("""
                INSERT OR IGNORE INTO activities (
                    id, name, type, sport_type,
                    distance_miles, moving_time_min, elapsed_time_min,
                    pace, average_speed, average_heartrate, max_heartrate,
                    total_elevation_gain, date, start_date,
                    has_heartrate, source, trainer, pool_length_meters, hk_source_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                activity_id, activity_name, w.type, w.type,
                round(distance_miles, 4) if distance_miles else 0.0,
                round(duration_min, 2), round(duration_min, 2),
                round(pace, 4) if pace else None,
                round(distance_m / w.duration_sec, 4) if distance_m and w.duration_sec else 0.0,
                round(w.avg_heartrate, 1) if w.avg_heartrate else None,
                round(w.max_heartrate, 1) if w.max_heartrate else None,
                0.0, date_str, start_date_local,
                1 if w.avg_heartrate else 0,
                "apple_health", 0,
                round(w.pool_length_meters, 2) if w.pool_length_meters else None,
                w.source_id,
            ))
            added += 1
            added_activities.append({"id": activity_id, "source_id": w.source_id})

        if w.swim_laps:
            conn.execute("DELETE FROM swim_laps WHERE activity_id = ?", (activity_id,))
            for lap in w.swim_laps:
                conn.execute("""
                    INSERT INTO swim_laps
                        (activity_id, lap_number, distance_meters, duration_seconds,
                         stroke_type, stroke_count, avg_heartrate, is_rest)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    activity_id, lap.lap_number,
                    lap.distance_meters or w.pool_length_meters,
                    lap.duration_seconds, lap.stroke_type,
                    lap.stroke_count, lap.avg_heartrate,
                    1 if lap.is_rest else 0,
                ))
            if w.pool_length_meters:
                conn.execute(
                    "UPDATE activities SET pool_length_meters = ? WHERE id = ?",
                    (round(w.pool_length_meters, 2), activity_id)
                )
        else:
            has_locations = bool(w.streams and w.streams.locations)
            has_distance  = bool(w.streams and w.streams.distance)
            if not has_locations and not has_distance:
                skipped += 1
                continue

        bundle = None
        locs = []
        if w.streams and w.streams.locations:
            locs = [loc.model_dump() for loc in w.streams.locations]
            hrs  = [hr.model_dump() for hr in w.streams.heartrate] if w.streams.heartrate else None
            bundle = from_healthkit_streams(locs, hrs)
        elif w.streams and w.streams.distance:
            dists = [d.model_dump() for d in w.streams.distance]
            hrs   = [hr.model_dump() for hr in w.streams.heartrate] if w.streams.heartrate else None
            bundle = from_distance_stream(dists, hrs)

        if bundle is not None and bundle.distance:
            splits = compute_splits(
                bundle,
                activity_id=activity_id,
                activity_name=activity_name,
                date_str=date_str,
                total_distance_miles=distance_miles or None,
            )
            if splits:
                svc.add_splits(splits)
                svc.compute_and_save_summaries(activity_id)
                splits_built += 1

            if locs:
                polyline_str = _encode_polyline(locs)
                start = locs[0]
                end = locs[-1]
                total_elev_m = sum(float(s.get('elevation_gain_meters') or 0) for s in splits)
                conn.execute(
                    """
                    UPDATE activities
                       SET map_polyline = ?, start_latlng = ?, end_latlng = ?,
                           start_lat = ?, start_lng = ?, end_lat = ?, end_lng = ?,
                           total_elevation_gain = CASE
                               WHEN ? > 0 THEN ? ELSE total_elevation_gain
                           END
                     WHERE id = ?
                    """,
                    (
                        polyline_str or None,
                        f"[{start['lat']},{start['lng']}]",
                        f"[{end['lat']},{end['lng']}]",
                        start['lat'], start['lng'], end['lat'], end['lng'],
                        total_elev_m, round(total_elev_m, 2), activity_id,
                    )
                )
            else:
                conn.execute("UPDATE activities SET trainer = 1 WHERE id = ?", (activity_id,))

    conn.commit()

    if added > 0 or splits_built > 0:
        svc._invalidate_all_caches()

    return {"added": added, "skipped": skipped, "splits_built": splits_built,
            "added_activities": added_activities}
