"""
Fitness & Fatigue Model — CTL / ATL / TSB using TRIMP.

Background
----------
Banister's TRIMP (Training Impulse, 1991) quantifies the physiological stress
of a single workout as a function of duration and heart rate:

    TRIMP = D × ΔHR × k × e^(b × ΔHR)

where
    D    = duration in minutes
    ΔHR  = (avg_HR - resting_HR) / (max_HR - resting_HR)   [0-1]
    b    = 1.92 for men (standard Banister value)
    k    = 0.64

CTL / ATL are exponential moving averages of daily TRIMP:

    CTL[d] = CTL[d-1] + (stress[d] - CTL[d-1]) / 42
    ATL[d] = ATL[d-1] + (stress[d] - ATL[d-1]) / 7

TSB (form) = CTL[d-1] - ATL[d-1]  (yesterday's fitness minus fatigue)

Interpretation
--------------
  TSB > +10  : Fresh / undertrained — good for a race
  TSB 0-10   : Optimal training zone
  TSB -10-0  : Normal fatigue, productive training load
  TSB < -10  : Accumulated fatigue — risk of overreaching
  TSB < -25  : High overtraining risk

For activities without HR data the load is estimated from pace/distance
using a conservative intensity multiplier so those workouts still
contribute to the fatigue curve without over-inflating it.

HR parameter auto-detection
----------------------------
max_HR  = 97th-percentile of all recorded max_heartrate values (avoids
          sensor spikes; updates as more data accumulates)
rest_HR = user-settable via user_settings table, defaults to 60 bpm
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from backend.services.database import get_conn

logger = logging.getLogger(__name__)

# EMA decay windows (days)
_CTL_DAYS = 42
_ATL_DAYS = 7

# TRIMP constants (Banister, gender-neutral approximation)
_TRIMP_B = 1.92
_TRIMP_K = 0.64

# Fallbacks used when HR data is sparse
_DEFAULT_RESTING_HR = 60.0
_DEFAULT_MAX_HR     = 190.0

# Pace intensity brackets for no-HR estimation (min/mile → intensity factor 0-1)
_PACE_INTENSITY = [
    (7.0,  0.85),   # < 7 min/mi  → hard
    (8.5,  0.72),   # 7-8.5       → threshold
    (10.0, 0.58),   # 8.5-10      → aerobic
    (12.0, 0.45),   # 10-12       → easy
    (float("inf"), 0.35),  # > 12 → very easy / walking
]


# ── HR parameter detection ─────────────────────────────────────────────────────

def _get_hr_params() -> tuple[float, float]:
    """
    Return (resting_hr, max_hr).
    max_hr is auto-detected from the 97th percentile of recorded max_heartrate.
    resting_hr is read from user_settings or falls back to 60 bpm.
    """
    conn = get_conn()

    # Resting HR from settings
    row = conn.execute(
        "SELECT value FROM user_settings WHERE key = 'resting_hr'"
    ).fetchone()
    resting_hr = float(row["value"]) if row else _DEFAULT_RESTING_HR

    # Max HR: percentile from historical data
    rows = conn.execute("""
        SELECT max_heartrate
        FROM   activities
        WHERE  has_heartrate = 1
          AND  max_heartrate > 100
        ORDER  BY max_heartrate ASC
    """).fetchall()

    if len(rows) >= 10:
        vals = [r[0] for r in rows]
        idx  = int(len(vals) * 0.97)
        max_hr = float(vals[min(idx, len(vals) - 1)])
        # Sanity clamp
        max_hr = max(160.0, min(220.0, max_hr))
    else:
        max_hr = _DEFAULT_MAX_HR

    return resting_hr, max_hr


# ── Per-workout stress computation ────────────────────────────────────────────

def _trimp(duration_min: float, avg_hr: float,
           resting_hr: float, max_hr: float) -> float:
    """Banister TRIMP for a single workout."""
    hr_range = max_hr - resting_hr
    if hr_range <= 0 or avg_hr <= resting_hr:
        # Degenerate case — return minimal load based on duration alone
        return duration_min * 0.30

    delta = (avg_hr - resting_hr) / hr_range
    delta = max(0.0, min(1.0, delta))
    return duration_min * delta * _TRIMP_K * math.exp(_TRIMP_B * delta)


def _estimated_load(distance_miles: float, pace: float) -> float:
    """
    Estimate training stress for activities without HR data.
    pace = min/mile (lower = faster).
    """
    if not distance_miles or distance_miles <= 0:
        return 0.0

    # Duration in minutes
    duration_min = distance_miles * max(pace, 4.0) if pace and pace > 0 else distance_miles * 10.0

    # Intensity factor from pace
    intensity = 0.35
    for threshold, factor in _PACE_INTENSITY:
        if pace < threshold:
            intensity = factor
            break

    return duration_min * intensity


# ── Main computation ──────────────────────────────────────────────────────────

def get_fitness_data(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
) -> List[dict]:
    """
    Compute and return daily CTL / ATL / TSB time series.

    Parameters
    ----------
    date_from : YYYY-MM-DD — start of the window to *return* (CTL is always
                computed from the very first activity so the values are accurate).
    date_to   : YYYY-MM-DD — end of the window; defaults to today.

    Returns
    -------
    List of dicts: { date, ctl, atl, tsb, daily_stress }
    """
    conn = get_conn()
    resting_hr, max_hr = _get_hr_params()

    # Load all activities (needed for accurate EMA even when output is trimmed)
    rows = conn.execute("""
        SELECT date,
               moving_time_min,
               average_heartrate,
               has_heartrate,
               distance_miles,
               pace
        FROM   activities
        WHERE  date IS NOT NULL
          AND  moving_time_min > 0
        ORDER  BY date ASC
    """).fetchall()

    if not rows:
        return []

    # Aggregate daily stress (multiple workouts on the same day are summed)
    daily_stress: dict[str, float] = {}
    for row in rows:
        date_str    = row["date"]
        dur         = float(row["moving_time_min"] or 0.0)
        avg_hr      = float(row["average_heartrate"] or 0.0)
        has_hr      = bool(row["has_heartrate"])
        distance    = float(row["distance_miles"]   or 0.0)
        pace        = float(row["pace"]              or 0.0)

        if dur <= 0:
            continue

        if has_hr and avg_hr > resting_hr + 5:
            stress = _trimp(dur, avg_hr, resting_hr, max_hr)
        else:
            stress = _estimated_load(distance, pace)

        daily_stress[date_str] = daily_stress.get(date_str, 0.0) + stress

    if not daily_stress:
        return []

    # Date range
    first_date = datetime.strptime(sorted(daily_stress)[0], "%Y-%m-%d")
    last_date  = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    if date_to:
        try:
            last_date = min(last_date, datetime.strptime(date_to, "%Y-%m-%d"))
        except ValueError:
            pass

    output_start: Optional[datetime] = None
    if date_from:
        try:
            output_start = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            pass

    # Walk every calendar day, updating EMA
    results: List[dict] = []
    ctl = 0.0
    atl = 0.0
    current = first_date

    while current <= last_date:
        ds = current.strftime("%Y-%m-%d")
        stress = daily_stress.get(ds, 0.0)

        # TSB reflects how you *enter* the day (before today's workout)
        tsb = round(ctl - atl, 2)

        # Update EMA
        ctl = ctl + (stress - ctl) / _CTL_DAYS
        atl = atl + (stress - atl) / _ATL_DAYS

        if output_start is None or current >= output_start:
            results.append({
                "date":         ds,
                "ctl":          round(ctl, 2),
                "atl":          round(atl, 2),
                "tsb":          tsb,
                "daily_stress": round(stress, 2),
            })

        current += timedelta(days=1)

    return results


def get_readiness(ctl: float, atl: float, tsb: float) -> dict:
    """
    Map CTL/ATL/TSB snapshot to a readiness score and recommendation.
    Called by the readiness endpoint (Opportunity B in the roadmap).
    """
    # Primary signal: TSB
    # Adjust raw TSB to 0-100 score
    # Typical TSB range: -40 (deep fatigue) to +20 (very fresh)
    score = int(max(0, min(100, (tsb + 40) / 60 * 100)))

    if score >= 85:
        zone = "peak"
        recommendation = "Peak form — consider a race or time trial"
    elif score >= 70:
        zone = "ready"
        recommendation = "Ready for intensity — tempo, intervals, or a hard long run"
    elif score >= 50:
        zone = "moderate"
        recommendation = "Moderate load — solid aerobic or steady effort"
    elif score >= 30:
        zone = "easy"
        recommendation = "Stay easy — recovery run or rest"
    else:
        zone = "recovery"
        recommendation = "Recovery day — rest, walk, or light cross-train only"

    return {
        "score":          score,
        "zone":           zone,
        "recommendation": recommendation,
        "ctl":            round(ctl, 1),
        "atl":            round(atl, 1),
        "tsb":            round(tsb, 1),
    }
