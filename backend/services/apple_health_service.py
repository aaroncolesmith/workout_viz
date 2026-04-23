"""
Apple Health XML import service.

Apple's export format: a ZIP containing export.xml (plus GPX route files).
The XML can be 100-500 MB; we use ElementTree iterparse (streaming) to avoid
loading the whole document into memory.

Two-pass strategy
-----------------
Pass 1 — collect all <Workout> elements into a list (small data per workout).
Pass 2 — stream <Record type="HKQuantityTypeIdentifierHeartRate"> records;
          binary-search each sample against sorted workout time windows to
          accumulate avg/max HR without storing every sample.

IDs
---
Apple Health activities get *negative* IDs derived from a hash of
(type + start_date_iso).  Strava IDs are always positive, so there is no
collision risk.  Re-importing is idempotent: same activity → same ID.

Deduplication
-------------
Before inserting, check for an existing activity of the same type whose
start_date is within ±60 seconds.  Strava records take priority (not overwritten).
"""

import bisect
import hashlib
import io
import logging
import threading
import zipfile
from datetime import datetime
from typing import Optional
from xml.etree.ElementTree import iterparse

from backend.services.database import get_conn

logger = logging.getLogger(__name__)

# ── HKWorkoutActivityType → our activity type strings ──────────────────────
ACTIVITY_TYPE_MAP: dict[str, str] = {
    'HKWorkoutActivityTypeRunning':                    'Run',
    'HKWorkoutActivityTypeCycling':                    'Ride',
    'HKWorkoutActivityTypeWalking':                    'Walk',
    'HKWorkoutActivityTypeHiking':                     'Hike',
    'HKWorkoutActivityTypeSwimming':                   'Swim',
    'HKWorkoutActivityTypeTraditionalStrengthTraining':'WeightTraining',
    'HKWorkoutActivityTypeFunctionalStrengthTraining': 'Workout',
    'HKWorkoutActivityTypeHIIT':                       'HIIT',
    'HKWorkoutActivityTypeHighIntensityIntervalTraining': 'HIIT',
    'HKWorkoutActivityTypeYoga':                       'Yoga',
    'HKWorkoutActivityTypeCrossTraining':              'Crossfit',
    'HKWorkoutActivityTypeElliptical':                 'Elliptical',
    'HKWorkoutActivityTypeStairClimbing':              'StairStepper',
    'HKWorkoutActivityTypeRowing':                     'Rowing',
    'HKWorkoutActivityTypePilates':                    'Pilates',
    'HKWorkoutActivityTypeDance':                      'Dance',
    'HKWorkoutActivityTypeMixedCardio':                'Workout',
    'HKWorkoutActivityTypeCoreTraining':               'CoreTraining',
    'HKWorkoutActivityTypeCooldown':                   'Cooldown',
    'HKWorkoutActivityTypeMindAndBody':                'MindAndBody',
    'HKWorkoutActivityTypePreparationAndRecovery':     'Recovery',
}

# ── Background import state ────────────────────────────────────────────────
_state: dict = {
    'status':     'idle',   # idle | running | done | error
    'message':    '',
    'parsed':     0,
    'added':      0,
    'skipped':    0,
    'failed':     0,
    'started_at': None,
    'error':      None,
}
_lock = threading.Lock()


def get_import_status() -> dict:
    with _lock:
        return dict(_state)


def start_import(file_bytes: bytes, filename: str) -> dict:
    """Kick off a background import.  Returns immediately."""
    with _lock:
        if _state['status'] == 'running':
            return {'status': 'already_running'}
        _state.update({
            'status':     'running',
            'message':    'Starting…',
            'parsed':     0,
            'added':      0,
            'skipped':    0,
            'failed':     0,
            'started_at': datetime.now().isoformat(),
            'error':      None,
        })

    t = threading.Thread(target=_run_import, args=(file_bytes, filename), daemon=True)
    t.start()
    return {'status': 'started'}


# ── Internal helpers ───────────────────────────────────────────────────────

def _set(**kw):
    with _lock:
        _state.update(kw)


def _ah_id(activity_type: str, start_date_iso: str) -> int:
    """Stable negative integer ID — never collides with Strava's positive IDs.
    Uses 6 bytes (48 bits) so the value fits within JS Number.MAX_SAFE_INTEGER (2^53).
    """
    digest = hashlib.sha256(f"{activity_type}:{start_date_iso}".encode()).digest()
    val = int.from_bytes(digest[:6], 'big')
    return -(val or 1)


def _parse_dt(s: str) -> Optional[datetime]:
    """Parse Apple Health date: '2026-04-01 07:30:00 -0700'"""
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y-%m-%d %H:%M:%S %z')
    except ValueError:
        return None


# ── Pass 1: collect workouts ───────────────────────────────────────────────

def _parse_workouts(xml_bytes: bytes) -> list:
    """
    Stream through XML collecting <Workout> elements.
    Uses the root.clear() trick to prevent memory accumulation.
    """
    workouts = []

    ctx = iterparse(io.BytesIO(xml_bytes), events=('start', 'end'))
    ctx = iter(ctx)
    _, root = next(ctx)  # grab root element

    for event, elem in ctx:
        if event != 'end' or elem.tag != 'Workout':
            continue

        hk_type = elem.get('workoutActivityType', '')
        activity_type = ACTIVITY_TYPE_MAP.get(hk_type)
        if not activity_type:
            root.clear()
            continue

        start_dt = _parse_dt(elem.get('startDate'))
        end_dt   = _parse_dt(elem.get('endDate'))
        if not start_dt or not end_dt:
            root.clear()
            continue

        duration_sec = (end_dt - start_dt).total_seconds()
        if duration_sec < 60:           # skip sub-1-min artefacts
            root.clear()
            continue

        # Distance
        dist_val  = elem.get('totalDistance')
        dist_unit = elem.get('totalDistanceUnit', 'mi')
        dist_m: Optional[float] = None
        if dist_val:
            d = float(dist_val)
            if dist_unit in ('mi', 'mile', 'miles'):
                dist_m = d * 1609.344
            elif dist_unit in ('km',):
                dist_m = d * 1000.0
            elif dist_unit in ('m', 'meters', 'meter'):
                dist_m = d
            else:
                dist_m = d * 1609.344  # default assume miles (Apple Health default)

        start_iso = start_dt.isoformat()
        start_local = start_dt.strftime('%Y-%m-%dT%H:%M:%S')

        workouts.append({
            'id':               _ah_id(activity_type, start_iso),
            'type':             activity_type,
            'sport_type':       activity_type,
            'name':             f'{activity_type} — {start_dt.strftime("%-m/%-d/%y")}',
            'start_date':       start_iso,
            'start_date_local': start_local,
            'date':             start_dt.strftime('%Y-%m-%d'),
            'start_ts':         start_dt.timestamp(),
            'end_ts':           end_dt.timestamp(),
            'duration_sec':     duration_sec,
            'dist_m':           dist_m,
            'calories':         float(elem.get('totalEnergyBurned') or 0) or None,
            'source':           'apple_health',
            'source_name':      elem.get('sourceName', ''),
            'hr_sum':           0.0,
            'hr_count':         0,
            'hr_max':           0.0,
        })
        root.clear()

    return workouts


# ── Pass 2: match HR samples ───────────────────────────────────────────────

def _match_hr_data(xml_bytes: bytes, workouts: list):
    """
    Stream HR records and accumulate running sum/count/max per workout.
    Workouts must be sorted by start_ts before calling.
    """
    if not workouts:
        return

    starts = [w['start_ts'] for w in workouts]

    ctx = iterparse(io.BytesIO(xml_bytes), events=('start', 'end'))
    ctx = iter(ctx)
    _, root = next(ctx)

    for event, elem in ctx:
        if event != 'end' or elem.tag != 'Record':
            continue
        if elem.get('type') != 'HKQuantityTypeIdentifierHeartRate':
            root.clear()
            continue

        val_str = elem.get('value')
        ts_str  = elem.get('startDate')
        if not val_str or not ts_str:
            root.clear()
            continue

        dt = _parse_dt(ts_str)
        if not dt:
            root.clear()
            continue

        ts  = dt.timestamp()
        val = float(val_str)

        # Binary search: find workouts whose window contains this timestamp
        idx = bisect.bisect_right(starts, ts) - 1
        for i in range(max(0, idx), min(len(workouts), idx + 3)):
            w = workouts[i]
            if w['start_ts'] <= ts <= w['end_ts']:
                w['hr_sum']   += val
                w['hr_count'] += 1
                if val > w['hr_max']:
                    w['hr_max'] = val
        root.clear()


# ── DB insertion ───────────────────────────────────────────────────────────

def _insert_workouts(workouts: list) -> tuple[int, int, int]:
    conn = get_conn()
    added = skipped = failed = 0

    for w in workouts:
        try:
            # Dedup: same type + start within ±60s
            dup = conn.execute("""
                SELECT id FROM activities
                WHERE type = ?
                  AND ABS(CAST(strftime('%s', start_date) AS INTEGER) - ?) < 60
                LIMIT 1
            """, (w['type'], int(w['start_ts']))).fetchone()

            if dup:
                skipped += 1
                continue

            dist_miles = (w['dist_m'] / 1609.344) if w['dist_m'] else 0.0
            avg_speed  = (w['dist_m'] / w['duration_sec']) if w['dist_m'] and w['duration_sec'] > 0 else 0.0
            avg_hr     = round(w['hr_sum'] / w['hr_count'], 1) if w['hr_count'] > 0 else None
            max_hr     = round(w['hr_max'], 1) if w['hr_max'] > 0 else None

            # Pace: min/mile — only meaningful for GPS activities
            pace = None
            if dist_miles > 0 and w['type'] in ('Run', 'Walk', 'Hike'):
                pace = (w['duration_sec'] / 60.0) / dist_miles

            moving_time_sec = int(w['duration_sec'])

            conn.execute("""
                INSERT OR IGNORE INTO activities (
                    id, name, type, sport_type,
                    start_date, start_date_local, date,
                    distance, distance_miles,
                    moving_time, elapsed_time,
                    moving_time_min, moving_time_hr,
                    elapsed_time_min, elapsed_time_hours,
                    average_speed,
                    average_heartrate, max_heartrate, has_heartrate,
                    total_elevation_gain,
                    pace,
                    source
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?,
                    ?,
                    ?, ?, ?,
                    ?,
                    ?,
                    ?
                )
            """, (
                w['id'], w['name'], w['type'], w['sport_type'],
                w['start_date'], w['start_date_local'], w['date'],
                w['dist_m'] or 0.0, dist_miles,
                moving_time_sec, moving_time_sec,
                round(moving_time_sec / 60.0, 2), round(moving_time_sec / 3600.0, 4),
                round(moving_time_sec / 60.0, 2), round(moving_time_sec / 3600.0, 4),
                avg_speed,
                avg_hr, max_hr, 1 if avg_hr else 0,
                0.0,
                round(pace, 4) if pace else None,
                'apple_health',
            ))
            conn.commit()
            added += 1

        except Exception as e:
            logger.warning(f"Failed to insert Apple Health activity {w.get('start_date')}: {e}")
            failed += 1

    return added, skipped, failed


# ── Main worker ────────────────────────────────────────────────────────────

def _run_import(file_bytes: bytes, filename: str):
    try:
        # --- Unzip if needed -------------------------------------------------
        fn = filename.lower()
        if fn.endswith('.zip'):
            _set(message='Extracting ZIP…')
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                xml_names = [n for n in zf.namelist() if n.endswith('export.xml')]
                if not xml_names:
                    raise ValueError("No export.xml found in the ZIP. "
                                     "Export via Health app → your avatar → Export All Health Data.")
                xml_bytes = zf.read(xml_names[0])
        elif fn.endswith('.xml'):
            xml_bytes = file_bytes
        else:
            raise ValueError("Unsupported file type — upload the export.zip or export.xml from Apple Health.")

        size_mb = len(xml_bytes) / 1_048_576
        logger.info(f"Apple Health XML size: {size_mb:.1f} MB")

        # --- Pass 1: workouts ------------------------------------------------
        _set(message=f'Scanning workouts ({size_mb:.0f} MB)…')
        workouts = _parse_workouts(xml_bytes)
        total = len(workouts)
        logger.info(f"Apple Health: found {total} workouts")
        _set(message=f'Found {total} workouts — matching HR data…', parsed=total)

        # Sort by start time for binary search in pass 2
        workouts.sort(key=lambda w: w['start_ts'])

        # --- Pass 2: HR matching ----------------------------------------------
        _set(message=f'Matching heart rate data ({size_mb:.0f} MB, second pass)…')
        _match_hr_data(xml_bytes, workouts)

        hr_matched = sum(1 for w in workouts if w['hr_count'] > 0)
        logger.info(f"Apple Health: HR data matched for {hr_matched}/{total} workouts")

        # --- Insert -----------------------------------------------------------
        _set(message=f'Inserting {total} workouts into database…')
        added, skipped, failed = _insert_workouts(workouts)

        # Invalidate DataService caches so next page load reflects new data
        try:
            from backend.services.data_service import get_data_service
            get_data_service()._invalidate_all_caches()
        except Exception:
            pass

        _set(
            status='done',
            message=f'Done — {added} added, {skipped} skipped (duplicates), {failed} failed',
            added=added,
            skipped=skipped,
            failed=failed,
        )
        logger.info(f"Apple Health import complete: added={added} skipped={skipped} failed={failed}")

    except Exception as e:
        import traceback
        logger.error(f"Apple Health import error: {e}\n{traceback.format_exc()}")
        _set(status='error', message=str(e), error=str(e))
