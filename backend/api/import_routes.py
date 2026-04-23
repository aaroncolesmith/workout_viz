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


class HKSyncRequest(BaseModel):
    workouts: List[HKWorkout]


class HKSyncResponse(BaseModel):
    added: int
    skipped: int


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

    import hashlib, math
    from datetime import datetime, timezone
    from backend.services.data_service import get_data_service

    def _hk_id(source_id: str) -> int:
        # 6 bytes (48 bits) — fits within JS Number.MAX_SAFE_INTEGER
        digest = hashlib.sha256(f"hk:{source_id}".encode()).digest()
        n = int.from_bytes(digest[:6], "big")
        return -(n or 1)

    STRENGTH_TYPES = {
        'WeightTraining', 'Workout', 'FunctionalStrengthTraining', 'CoreTraining',
        'HIIT', 'Yoga', 'Pilates', 'MindAndBody', 'Recovery', 'Cooldown',
        'Crossfit', 'Elliptical', 'StairStepper', 'Rowing',
    }

    added = skipped = 0
    conn = get_conn()

    for w in body.workouts:
        if w.duration_sec < 60:
            skipped += 1
            continue

        activity_id = _hk_id(w.source_id)
        duration_min = w.duration_sec / 60.0
        is_strength = w.type in STRENGTH_TYPES

        distance_m = w.distance_meters or 0.0
        distance_miles = distance_m / 1609.344
        pace = None
        if distance_miles > 0.05 and duration_min > 0:
            pace = duration_min / distance_miles

        # Parse start date
        try:
            start_dt = datetime.fromisoformat(w.start_date)
            date_str = start_dt.date().isoformat()
            start_date_local = start_dt.isoformat()
        except Exception:
            skipped += 1
            continue

        existing = conn.execute(
            "SELECT id FROM activities WHERE id = ?", (activity_id,)
        ).fetchone()
        if existing:
            skipped += 1
            continue

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
            f"{w.type} – {date_str}",
            w.type,
            w.type,
            round(distance_miles, 4) if distance_miles else 0.0,
            round(duration_min, 2),
            round(duration_min, 2),
            round(pace, 4) if pace else None,
            round(distance_m / w.duration_sec, 4) if distance_m and w.duration_sec else 0.0,
            round(w.avg_heartrate, 1) if w.avg_heartrate else None,
            round(w.max_heartrate, 1) if w.max_heartrate else None,
            0.0,  # elevation not available from HK basic sync
            date_str,
            start_date_local,
            1 if w.avg_heartrate else 0,
            "apple_health",
            0,
        ))
        added += 1

    conn.commit()

    if added > 0:
        get_data_service()._invalidate_all_caches()

    return {"added": added, "skipped": skipped}
