"""
Import API — Apple Health (and future sources).
"""
import os
from typing import List, Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Header
from pydantic import BaseModel

from backend.services.apple_health_service import start_import, get_import_status
from backend.services.database import get_conn
from backend.models import schemas

router = APIRouter(prefix="/api/import", tags=["import"])

# 256 MB limit — Apple Health exports are typically 50-200 MB
MAX_UPLOAD_BYTES = 256 * 1024 * 1024


@router.post("/apple-health", response_model=schemas.ImportStartResponse)
async def upload_apple_health(file: UploadFile = File(...)):
    """
    Accept an Apple Health export ZIP (or raw export.xml) and kick off a
    background import.  Poll GET /api/import/apple-health/status for progress.
    """
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 256 MB).")
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file.")

    result = start_import(contents, file.filename or "export.zip")
    return result


@router.get("/apple-health/status", response_model=schemas.ImportStatusResponse)
def apple_health_status():
    """Poll for import progress."""
    return get_import_status()


# ── HealthKit native sync (iOS companion app) ──────────────────────────────────

class HKLocationSample(BaseModel):
    """One GPS point from HKWorkoutRoute. `t` is seconds since workout start."""
    t:   float
    lat: float
    lng: float
    alt: Optional[float] = None


class HKHeartRateSample(BaseModel):
    t:   float
    bpm: float


class HKStreams(BaseModel):
    locations: List[HKLocationSample] = []
    heartrate: List[HKHeartRateSample] = []


class HKWorkout(BaseModel):
    """Single workout sent from the iOS HealthKit sync engine."""
    source_id: str              # stable local UUID from HK (used for dedup)
    type: str                   # e.g. "WeightTraining", "Running"
    start_date: str             # ISO8601: "2026-04-01T07:30:00-07:00"
    end_date: str
    duration_sec: float
    distance_meters: Optional[float] = None
    active_energy_kcal: Optional[float] = None
    avg_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    # Optional — when present, backend computes splits + fastest segments.
    streams: Optional[HKStreams] = None


class HKSyncRequest(BaseModel):
    workouts: List[HKWorkout]


class HKSyncResponse(BaseModel):
    added:        int
    skipped:      int
    splits_built: int = 0   # how many workouts got splits computed


def _require_healthkit_key(x_api_key: Optional[str] = Header(default=None)):
    expected = os.getenv("HEALTHKIT_API_KEY", "")
    if not expected:
        return  # key not configured — open in dev
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key.")


@router.post("/healthkit", response_model=HKSyncResponse)
def healthkit_sync(body: HKSyncRequest, x_api_key: Optional[str] = Header(default=None)):
    """
    Native iOS HealthKit sync endpoint.
    The iOS app sends batches of workouts as JSON; we upsert them into SQLite.
    Uses X-Api-Key header for auth (set HEALTHKIT_API_KEY env var on Railway).
    """
    _require_healthkit_key(x_api_key)

    import hashlib
    import polyline as _polyline
    from datetime import datetime
    from backend.services.data_service import get_data_service
    from backend.services.splits_service import from_healthkit_streams, compute_splits

    def _encode_polyline(locations: list, max_points: int = 1500) -> str:
        """Encode (lat, lng) points as a Google polyline, evenly downsampled."""
        if not locations:
            return ""
        n = len(locations)
        if n <= max_points:
            pts = [(loc['lat'], loc['lng']) for loc in locations]
        else:
            step = n / max_points
            pts = [(locations[int(i * step)]['lat'], locations[int(i * step)]['lng'])
                   for i in range(max_points)]
            # Always include the last point so the line closes visually.
            last = locations[-1]
            if pts[-1] != (last['lat'], last['lng']):
                pts.append((last['lat'], last['lng']))
        return _polyline.encode(pts)

    def _hk_id(source_id: str) -> int:
        # 6 bytes (48 bits) — fits within JS Number.MAX_SAFE_INTEGER
        digest = hashlib.sha256(f"hk:{source_id}".encode()).digest()
        n = int.from_bytes(digest[:6], "big")
        return -(n or 1)

    added = skipped = splits_built = 0
    conn = get_conn()
    svc = get_data_service()

    for w in body.workouts:
        if w.duration_sec < 60:
            skipped += 1
            continue

        activity_id = _hk_id(w.source_id)
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

        activity_name = f"{w.type} – {date_str}"
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
                    has_heartrate, source, trainer
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                activity_id,
                activity_name,
                w.type,
                w.type,
                round(distance_miles, 4) if distance_miles else 0.0,
                round(duration_min, 2),
                round(duration_min, 2),
                round(pace, 4) if pace else None,
                round(distance_m / w.duration_sec, 4) if distance_m and w.duration_sec else 0.0,
                round(w.avg_heartrate, 1) if w.avg_heartrate else None,
                round(w.max_heartrate, 1) if w.max_heartrate else None,
                0.0,  # elevation filled in from streams below, if available
                date_str,
                start_date_local,
                1 if w.avg_heartrate else 0,
                "apple_health",
                0,
            ))
            added += 1
        elif w.streams is None or not w.streams.locations:
            # No new data to add and no streams to backfill.
            skipped += 1
            continue

        # ── Streams: compute splits + fastest segments + polyline ─────────
        if w.streams and w.streams.locations:
            locs = [loc.model_dump() for loc in w.streams.locations]
            hrs  = [hr.model_dump()  for hr in w.streams.heartrate] if w.streams.heartrate else None
            bundle = from_healthkit_streams(locs, hrs)

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

            # Backfill derived geo fields on the activity row.
            polyline_str = _encode_polyline(locs)
            start = locs[0]
            end = locs[-1]
            total_elev_m = sum(float(s.get('elevation_gain_meters') or 0) for s in splits)
            conn.execute(
                """
                UPDATE activities
                   SET map_polyline = ?,
                       start_latlng = ?,
                       end_latlng   = ?,
                       start_lat    = ?,
                       start_lng    = ?,
                       end_lat      = ?,
                       end_lng      = ?,
                       total_elevation_gain = CASE
                           WHEN ? > 0 THEN ? ELSE total_elevation_gain
                       END
                 WHERE id = ?
                """,
                (
                    polyline_str or None,
                    f"[{start['lat']},{start['lng']}]",
                    f"[{end['lat']},{end['lng']}]",
                    start['lat'], start['lng'],
                    end['lat'],   end['lng'],
                    total_elev_m, round(total_elev_m, 2),
                    activity_id,
                )
            )

    conn.commit()

    if added > 0 or splits_built > 0:
        svc._invalidate_all_caches()

    return {"added": added, "skipped": skipped, "splits_built": splits_built}
