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

from backend.services.database import get_conn as _get_conn_raw

logger = logging.getLogger(__name__)

# ── HKSwimmingStrokeStyle int → name ─────────────────────────────────────
# Apple's enum: 0=unknown, 1=mixed, 2=freestyle, 3=backstroke,
#               4=breaststroke, 5=butterfly, 6=kickboard
_STROKE_STYLE = {
    '0': None,            # HKSwimmingStrokeStyleUnknown
    '1': 'mixed',
    '2': 'freestyle',
    '3': 'backstroke',
    '4': 'breaststroke',
    '5': 'butterfly',
    '6': 'kickboard',
}

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

# ── Background import state (per-user — this backend is multi-tenant) ──────
_IDLE_STATE: dict = {
    'status':     'idle',   # idle | running | done | error
    'message':    '',
    'parsed':     0,
    'added':      0,
    'skipped':    0,
    'failed':     0,
    'started_at': None,
    'error':      None,
}
_states: dict[str, dict] = {}   # user_id → import state
_lock = threading.Lock()


def get_import_status(user_id: str) -> dict:
    with _lock:
        return dict(_states.get(user_id) or _IDLE_STATE)


def start_import(file_bytes: bytes, filename: str, user_id: str) -> dict:
    """Kick off a background import for this user.  Returns immediately."""
    with _lock:
        existing = _states.get(user_id)
        if existing and existing['status'] == 'running':
            return {'status': 'already_running'}
        _states[user_id] = {
            **_IDLE_STATE,
            'status':     'running',
            'message':    'Starting…',
            'started_at': datetime.now().isoformat(),
        }

    t = threading.Thread(target=_run_import, args=(file_bytes, filename, user_id), daemon=True)
    t.start()
    return {'status': 'started'}


# ── Internal helpers ───────────────────────────────────────────────────────

def _set(user_id: str, **kw):
    with _lock:
        _states.setdefault(user_id, dict(_IDLE_STATE)).update(kw)


def _ah_id(activity_type: str, start_date_iso: str) -> int:
    """Stable negative integer ID — never collides with Strava's positive IDs.
    Uses 6 bytes (48 bits) so the value fits within JS Number.MAX_SAFE_INTEGER (2^53).
    """
    digest = hashlib.sha256(f"{activity_type}:{start_date_iso}".encode()).digest()
    val = int.from_bytes(digest[:6], 'big')
    return -(val or 1)


def hk_activity_id(source_id: str) -> int:
    """Stable negative ID for HealthKit-native syncs, from the HK workout UUID.
    6 bytes so the value fits within JS Number.MAX_SAFE_INTEGER.  The insert
    path (import_routes.healthkit_sync) and the delete-by-source endpoint both
    use this — any scheme change must go through here so they can't drift.
    """
    digest = hashlib.sha256(f"hk:{source_id}".encode()).digest()
    return -(int.from_bytes(digest[:6], 'big') or 1)


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

        # ── Swim-specific metadata + lap events ──────────────────────────
        pool_length_m: Optional[float] = None
        swim_laps: list = []
        if activity_type == 'Swim':
            for meta in elem.findall('MetadataEntry'):
                if meta.get('key') == 'HKSwimmingPoolLength':
                    try:
                        raw = float(meta.get('value', 0))
                        unit = meta.get('unit', 'm')
                        pool_length_m = raw * 0.9144 if unit == 'yd' else raw
                    except (ValueError, TypeError):
                        pass

            lap_num = 0
            for ev in elem.findall('WorkoutEvent'):
                if ev.get('type') != 'HKWorkoutEventTypeLap':
                    continue
                try:
                    dur = float(ev.get('durationInSeconds') or 0)
                except (ValueError, TypeError):
                    continue
                if dur <= 0:
                    continue
                lap_num += 1
                stroke_raw = None
                stroke_count = None
                for lm in ev.findall('MetadataEntry'):
                    k = lm.get('key', '')
                    if k == 'HKSwimmingStrokeStyle':
                        stroke_raw = _STROKE_STYLE.get(lm.get('value', ''))
                    elif k == 'HKSwimmingStrokeCount':
                        try:
                            stroke_count = int(float(lm.get('value', 0)))
                        except (ValueError, TypeError):
                            pass
                swim_laps.append({
                    'lap_number':      lap_num,
                    'distance_meters': pool_length_m,
                    'duration_seconds': dur,
                    'stroke_type':     stroke_raw,
                    'stroke_count':    stroke_count,
                    'is_rest':         0,
                })

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
            'pool_length_m':    pool_length_m,
            'swim_laps':        swim_laps,
        })
        root.clear()

    return workouts


# ── Pass 2: match HR samples + accumulate daily health metrics ─────────────

# HK Record type → (metric slug, aggregation).  Slugs must match
# health_metrics_service.KNOWN_METRICS.  'sum' metrics (steps, energy) are
# accumulated per source and the max source total per day wins — iPhone and
# Watch both record them, and a blind sum double-counts.
_QUANTITY_RECORD_MAP = {
    'HKQuantityTypeIdentifierRestingHeartRate':         ('resting_heartrate', 'avg'),
    'HKQuantityTypeIdentifierHeartRateVariabilitySDNN': ('hrv_sdnn', 'avg'),
    'HKQuantityTypeIdentifierVO2Max':                   ('vo2max', 'avg'),
    'HKQuantityTypeIdentifierRespiratoryRate':          ('respiratory_rate', 'avg'),
    'HKQuantityTypeIdentifierOxygenSaturation':         ('blood_oxygen', 'avg'),
    'HKQuantityTypeIdentifierStepCount':                ('steps', 'sum'),
    'HKQuantityTypeIdentifierActiveEnergyBurned':       ('active_energy', 'sum'),
    'HKQuantityTypeIdentifierBodyMass':                 ('body_mass', 'avg'),
}


class _DailyMetrics:
    """Accumulates <Record> elements into one sample per (metric, local day)."""

    def __init__(self):
        self._avg = {}    # (metric, day) -> [sum, count, min, max]
        self._sum = {}    # (metric, day, source) -> total
        self._sleep_asleep = []  # (start_dt, end_dt)
        self._sleep_inbed = []

    def add_record(self, rtype: str, elem):
        if rtype == 'HKCategoryTypeIdentifierSleepAnalysis':
            self._add_sleep(elem)
            return
        mapping = _QUANTITY_RECORD_MAP.get(rtype)
        if not mapping:
            return
        metric, agg = mapping
        val_str = elem.get('value')
        start = elem.get('startDate') or ''
        if not val_str or len(start) < 10:
            return
        try:
            val = float(val_str)
        except ValueError:
            return
        if not (val == val and abs(val) != float('inf')) or val < 0:
            return
        # Unit normalisation
        if metric == 'blood_oxygen' and val <= 1.0:
            val *= 100.0                      # fraction → %
        elif metric == 'body_mass' and elem.get('unit') == 'lb':
            val *= 0.453592                   # store kg (canonical)
        day = start[:10]                      # local day as recorded

        if agg == 'sum':
            key = (metric, day, elem.get('sourceName', ''))
            self._sum[key] = self._sum.get(key, 0.0) + val
        else:
            acc = self._avg.get((metric, day))
            if acc is None:
                self._avg[(metric, day)] = [val, 1, val, val]
            else:
                acc[0] += val
                acc[1] += 1
                acc[2] = min(acc[2], val)
                acc[3] = max(acc[3], val)

    def _add_sleep(self, elem):
        value = elem.get('value', '')
        start_dt = _parse_dt(elem.get('startDate'))
        end_dt = _parse_dt(elem.get('endDate'))
        if not start_dt or not end_dt or end_dt <= start_dt:
            return
        if 'Asleep' in value:
            self._sleep_asleep.append((start_dt, end_dt))
        elif value.endswith('InBed'):
            self._sleep_inbed.append((start_dt, end_dt))

    @staticmethod
    def _nightly_hours(intervals):
        """Merge overlapping intervals (multi-device double-count), then total
        hours per the day each merged session ENDS (the wake-up morning)."""
        merged = []
        for s, e in sorted(intervals):
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        by_day: dict = {}
        for s, e in merged:
            day = e.strftime('%Y-%m-%d')
            by_day[day] = by_day.get(day, 0.0) + (e - s).total_seconds() / 3600.0
        return by_day

    def samples(self) -> list:
        out = []
        for (metric, day), (total, count, vmin, vmax) in self._avg.items():
            out.append({'metric': metric, 'date': day,
                        'value': round(total / count, 2),
                        'min': round(vmin, 2), 'max': round(vmax, 2)})
        # sum metrics: best single source per day (avoids iPhone+Watch double count)
        best: dict = {}
        for (metric, day, _source), total in self._sum.items():
            key = (metric, day)
            if total > best.get(key, 0.0):
                best[key] = total
        for (metric, day), total in best.items():
            out.append({'metric': metric, 'date': day, 'value': round(total, 1)})
        for metric, intervals in (('sleep_asleep', self._sleep_asleep),
                                  ('sleep_in_bed', self._sleep_inbed)):
            for day, hours in self._nightly_hours(intervals).items():
                out.append({'metric': metric, 'date': day, 'value': round(hours, 2)})
        return out


def _scan_records(xml_bytes: bytes, workouts: list, daily: _DailyMetrics):
    """
    Single streaming pass over all <Record> elements:
      - HR samples → running sum/count/max per workout (binary search on the
        sorted workout windows);
      - daily-metric record types → the _DailyMetrics accumulator (BIO-4).
    Workouts must be sorted by start_ts before calling.
    """
    starts = [w['start_ts'] for w in workouts]

    ctx = iterparse(io.BytesIO(xml_bytes), events=('start', 'end'))
    ctx = iter(ctx)
    _, root = next(ctx)

    for event, elem in ctx:
        if event != 'end' or elem.tag != 'Record':
            continue
        rtype = elem.get('type')
        if rtype != 'HKQuantityTypeIdentifierHeartRate':
            daily.add_record(rtype, elem)
            root.clear()
            continue

        val_str = elem.get('value')
        ts_str  = elem.get('startDate')
        if not val_str or not ts_str or not workouts:
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

def _insert_workouts(workouts: list, conn=None) -> tuple[int, int, int]:
    if conn is None:
        raise RuntimeError("_insert_workouts requires a conn (user-scoped)")
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
                    source,
                    pool_length_meters
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
                    ?, ?
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
                round(w.get('pool_length_m'), 2) if w.get('pool_length_m') else None,
            ))

            # Insert swim laps if present
            for lap in w.get('swim_laps', []):
                conn.execute("""
                    INSERT INTO swim_laps
                        (activity_id, lap_number, distance_meters, duration_seconds,
                         stroke_type, stroke_count, is_rest)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    w['id'], lap['lap_number'], lap['distance_meters'],
                    lap['duration_seconds'], lap['stroke_type'],
                    lap['stroke_count'], lap['is_rest'],
                ))

            conn.commit()
            added += 1

        except Exception as e:
            logger.warning(f"Failed to insert Apple Health activity {w.get('start_date')}: {e}")
            failed += 1

    return added, skipped, failed


# ── Main worker ────────────────────────────────────────────────────────────

def _run_import(file_bytes: bytes, filename: str, user_id: str):
    try:
        # --- Unzip if needed -------------------------------------------------
        fn = filename.lower()
        if fn.endswith('.zip'):
            _set(user_id, message='Extracting ZIP…')
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
        _set(user_id, message=f'Scanning workouts ({size_mb:.0f} MB)…')
        workouts = _parse_workouts(xml_bytes)
        total = len(workouts)
        logger.info(f"Apple Health: found {total} workouts")
        _set(user_id, message=f'Found {total} workouts — matching HR data…', parsed=total)

        # Sort by start time for binary search in pass 2
        workouts.sort(key=lambda w: w['start_ts'])

        # --- Pass 2: HR matching + daily health metrics (BIO-4) ---------------
        _set(user_id, message=f'Matching heart rate + health data ({size_mb:.0f} MB, second pass)…')
        daily = _DailyMetrics()
        _scan_records(xml_bytes, workouts, daily)

        hr_matched = sum(1 for w in workouts if w['hr_count'] > 0)
        logger.info(f"Apple Health: HR data matched for {hr_matched}/{total} workouts")

        # --- Insert -----------------------------------------------------------
        _set(user_id, message=f'Inserting {total} workouts into database…')
        from backend.services.data_service import get_data_service
        svc = get_data_service(user_id)
        added, skipped, failed = _insert_workouts(workouts, conn=svc._conn())

        metric_samples = daily.samples()
        metric_days = 0
        if metric_samples:
            _set(user_id, message=f'Importing {len(metric_samples)} daily health metric samples…')
            from backend.services import health_metrics_service
            hm_result = health_metrics_service.upsert_metrics(svc._conn(), metric_samples)
            metric_days = hm_result['added'] + hm_result['updated']
            logger.info(f"Apple Health: daily metrics upserted {hm_result}")

        # Invalidate DataService caches so next page load reflects new data
        svc._invalidate_all_caches()

        _set(
            user_id,
            status='done',
            message=f'Done — {added} added, {skipped} skipped (duplicates), {failed} failed, '
                    f'{metric_days} daily health samples',
            added=added,
            skipped=skipped,
            failed=failed,
        )
        logger.info(f"Apple Health import complete: added={added} skipped={skipped} failed={failed}")

    except Exception as e:
        import traceback
        logger.error(f"Apple Health import error: {e}\n{traceback.format_exc()}")
        _set(user_id, status='error', message=str(e), error=str(e))
