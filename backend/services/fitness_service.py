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

def _get_hr_params(conn) -> tuple[float, float]:
    """Return (resting_hr, max_hr) from the user's DB connection."""

    # Resting HR: manual setting wins; otherwise the 30-day rolling mean of
    # the synced daily metric (RDY-1); the old 60 bpm default is last resort.
    row = conn.execute(
        "SELECT value FROM user_settings WHERE key = 'resting_hr'"
    ).fetchone()
    if row:
        resting_hr = float(row["value"])
    else:
        measured = conn.execute("""
            SELECT AVG(value) FROM health_metrics
            WHERE  metric = 'resting_heartrate'
              AND  date >= date('now', '-30 day')
        """).fetchone()[0]
        resting_hr = float(measured) if measured else _DEFAULT_RESTING_HR

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
    *,
    conn,
) -> List[dict]:
    """
    Compute and return daily CTL / ATL / TSB time series.

    Parameters
    ----------
    date_from : YYYY-MM-DD — start of the window to *return*.
    date_to   : YYYY-MM-DD — end of the window; defaults to today.
    conn      : SQLCipher connection for the current user's DB.
    """
    resting_hr, max_hr = _get_hr_params(conn)

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
        stress = _activity_load(row, resting_hr, max_hr)
        if stress <= 0:
            continue
        daily_stress[row["date"]] = daily_stress.get(row["date"], 0.0) + stress

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


def _activity_load(row, resting_hr: float, max_hr: float) -> float:
    """Training load for one activity row — HR TRIMP when available, pace
    estimation otherwise.  Single definition shared by the fitness curve and
    relative effort so the two can't disagree."""
    dur    = float(row["moving_time_min"] or 0.0)
    avg_hr = float(row["average_heartrate"] or 0.0)
    if dur <= 0:
        return 0.0
    if bool(row["has_heartrate"]) and avg_hr > resting_hr + 5:
        return _trimp(dur, avg_hr, resting_hr, max_hr)
    return _estimated_load(float(row["distance_miles"] or 0.0), float(row["pace"] or 0.0))


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{['st', 'nd', 'rd'][n % 10 - 1] if n % 10 in (1, 2, 3) else 'th'}"


def get_relative_effort(activity_id: int, *, conn) -> Optional[dict]:
    """
    CMP-2 — one activity's TRIMP as a percentile of the trailing 90 days.

    Works for every activity type (strength/swim included): HR TRIMP when
    available, pace/distance estimation otherwise.  Answers "was this harder
    *for me*" independent of pace, distance, or sport.
    """
    _COLS = "moving_time_min, average_heartrate, has_heartrate, distance_miles, pace"
    act = conn.execute(
        f"SELECT date, {_COLS} FROM activities WHERE id = ?", (activity_id,)
    ).fetchone()
    if not act or not act["date"]:
        return None

    resting_hr, max_hr = _get_hr_params(conn)
    target_load = _activity_load(act, resting_hr, max_hr)
    if target_load <= 0:
        return None

    try:
        date_from = (datetime.strptime(act["date"], "%Y-%m-%d")
                     - timedelta(days=90)).strftime("%Y-%m-%d")
    except ValueError:
        return None

    rows = conn.execute(f"""
        SELECT {_COLS} FROM activities
        WHERE  date >= ? AND date <= ? AND moving_time_min > 0
    """, (date_from, act["date"])).fetchall()
    loads = [ld for ld in (_activity_load(r, resting_hr, max_hr) for r in rows) if ld > 0]
    if not loads:
        return None

    n = len(loads)
    harder = sum(1 for ld in loads if ld > target_load + 1e-9)
    rank = harder + 1
    percentile = round(100.0 * (n - harder) / n, 1)
    return {
        "trimp":      round(target_load, 1),
        "percentile": percentile,
        "rank":       rank,
        "of":         n,
        "label":      f"{_ordinal(rank)} hardest of {n} efforts in the last 90 days",
    }


def _zone_for(score: int) -> tuple[str, str]:
    if score >= 85:
        return "peak", "Peak form — consider a race or time trial"
    if score >= 70:
        return "ready", "Ready for intensity — tempo, intervals, or a hard long run"
    if score >= 50:
        return "moderate", "Moderate load — solid aerobic or steady effort"
    if score >= 30:
        return "easy", "Stay easy — recovery run or rest"
    return "recovery", "Recovery day — rest, walk, or light cross-train only"


def get_readiness(ctl: float, atl: float, tsb: float) -> dict:
    """
    Map CTL/ATL/TSB snapshot to a readiness score and recommendation.
    Called by the readiness endpoint (Opportunity B in the roadmap).
    """
    # Primary signal: TSB
    # Adjust raw TSB to 0-100 score
    # Typical TSB range: -40 (deep fatigue) to +20 (very fresh)
    score = int(max(0, min(100, (tsb + 40) / 60 * 100)))
    zone, recommendation = _zone_for(score)

    return {
        "score":          score,
        "zone":           zone,
        "recommendation": recommendation,
        "ctl":            round(ctl, 1),
        "atl":            round(atl, 1),
        "tsb":            round(tsb, 1),
    }


# ── Readiness v2 (RDY-2): training load + morning physiology ─────────────────

_BODY_FRESH_DAYS = 2      # a metric older than this can't describe *today*
_FACTOR_WEIGHTS = {"load": 0.5, "hrv": 0.2, "rhr": 0.15, "sleep": 0.15}


def _clamp_score(v: float) -> int:
    return int(max(0, min(100, round(v))))


def get_readiness_v2(*, conn) -> dict:
    """
    Blend the TSB load score with same-morning deviations of HRV, resting HR,
    and sleep from their 30-day baselines.  Every factor is explainable —
    the response carries per-factor scores and a one-line "why" so the score
    is never a black box.  Missing/stale body metrics simply drop out and the
    weights renormalise (a user with no Watch data gets the pure load score).
    """
    from datetime import date as _date
    from backend.services import health_metrics_service as hm

    data = get_fitness_data(conn=conn)
    if not data:
        return {"score": 50, "zone": "moderate",
                "recommendation": "Not enough data yet — sync more activities.",
                "ctl": 0, "atl": 0, "tsb": 0, "factors": [], "why": None}

    latest = data[-1]
    tsb = latest["tsb"]
    load_score = _clamp_score((tsb + 40) / 60 * 100)
    factors = [{
        "name": "Training load",
        "score": load_score,
        "weight": _FACTOR_WEIGHTS["load"],
        "detail": f"Form (TSB) {tsb:+.1f} — "
                  f"{'fresh' if tsb > 5 else 'fatigued' if tsb < -10 else 'normal training fatigue'}",
    }]

    today = _date.today()

    def _fresh(cmp_block) -> bool:
        if not cmp_block or cmp_block.get("avg_30d") is None:
            return False
        try:
            anchor = _date.fromisoformat(cmp_block["date"])
        except (TypeError, ValueError):
            return False
        return (today - anchor).days <= _BODY_FRESH_DAYS

    # HRV: below baseline = accumulated stress.  ±20% swings the full scale.
    c = hm.get_metric_comparison(conn, "hrv_sdnn")
    if _fresh(c):
        dev_pct = (c["today"] - c["avg_30d"]) / c["avg_30d"] * 100
        factors.append({
            "name": "HRV",
            "score": _clamp_score(50 + dev_pct * 2.5),
            "weight": _FACTOR_WEIGHTS["hrv"],
            "detail": f"HRV {c['today']:.0f} ms, {dev_pct:+.0f}% vs your 30-day baseline",
        })

    # Resting HR: above baseline = stress/illness.  ±10% swings the full scale.
    c = hm.get_metric_comparison(conn, "resting_heartrate")
    if _fresh(c):
        dev_pct = (c["today"] - c["avg_30d"]) / c["avg_30d"] * 100
        factors.append({
            "name": "Resting HR",
            "score": _clamp_score(50 - dev_pct * 5),
            "weight": _FACTOR_WEIGHTS["rhr"],
            "detail": f"Resting HR {c['today']:.0f} bpm, "
                      f"{c['vs_30d_avg']:+.1f} vs your 30-day baseline",
        })

    # Sleep: last night vs baseline.  ±25% swings the full scale.
    c = hm.get_metric_comparison(conn, "sleep_asleep")
    if _fresh(c):
        dev_pct = (c["today"] - c["avg_30d"]) / c["avg_30d"] * 100
        h, m = int(c["today"]), int(round((c["today"] % 1) * 60))
        factors.append({
            "name": "Sleep",
            "score": _clamp_score(50 + dev_pct * 2),
            "weight": _FACTOR_WEIGHTS["sleep"],
            "detail": f"Slept {h}h {m:02d}m, {dev_pct:+.0f}% vs your 30-day average",
        })

    total_w = sum(f["weight"] for f in factors)
    blended = _clamp_score(sum(f["score"] * f["weight"] for f in factors) / total_w)
    zone, recommendation = _zone_for(blended)

    # When physiology moves the needle vs load alone, say so explicitly.
    if len(factors) > 1:
        if blended <= load_score - 10:
            recommendation = f"Body signals suggest backing off: {recommendation[0].lower()}{recommendation[1:]}"
        elif blended >= load_score + 10:
            recommendation = f"Body signals look strong: {recommendation[0].lower()}{recommendation[1:]}"

    return {
        "score":          blended,
        "zone":           zone,
        "recommendation": recommendation,
        "ctl":            round(latest["ctl"], 1),
        "atl":            round(latest["atl"], 1),
        "tsb":            round(tsb, 1),
        "factors":        factors,
        "why":            " · ".join(f["detail"] for f in factors),
    }


def get_readiness_history(days: int = 90, *, conn) -> List[dict]:
    """
    RDY-4 — the blended readiness score for each of the last `days` days,
    computed exactly as get_readiness_v2 would have scored that morning:
    TSB from the fitness curve plus that day's HRV/RHR/sleep deviations
    against a trailing 30-day baseline ending the day before.  Days where
    the user trained hard (stress above CTL) on a sub-30 morning are
    flagged `hard_on_red` for chart annotation.
    """
    from datetime import date as _date
    from backend.services.health_metrics_service import _load_series, _window_mean

    fitness = get_fitness_data(conn=conn)
    if not fitness:
        return []
    window = fitness[-days:]

    series = {m: _load_series(conn, m)
              for m in ("hrv_sdnn", "resting_heartrate", "sleep_asleep")}

    # (metric, weight, per-%-deviation slope) — same scales as get_readiness_v2
    specs = [("hrv_sdnn", _FACTOR_WEIGHTS["hrv"], 2.5),
             ("resting_heartrate", _FACTOR_WEIGHTS["rhr"], -5.0),
             ("sleep_asleep", _FACTOR_WEIGHTS["sleep"], 2.0)]

    out = []
    for point in window:
        try:
            d = _date.fromisoformat(point["date"])
        except (TypeError, ValueError):
            continue

        load_score = _clamp_score((point["tsb"] + 40) / 60 * 100)
        weighted = load_score * _FACTOR_WEIGHTS["load"]
        total_w = _FACTOR_WEIGHTS["load"]

        for metric, weight, slope in specs:
            by_date = series[metric]
            val = by_date.get(d)
            if val is None:
                continue
            base = _window_mean(by_date, d - timedelta(days=1), 30)
            if not base:
                continue
            dev_pct = (val - base) / base * 100
            weighted += _clamp_score(50 + dev_pct * slope) * weight
            total_w += weight

        score = _clamp_score(weighted / total_w)
        out.append({
            "date":         point["date"],
            "score":        score,
            "zone":         _zone_for(score)[0],
            "load_score":   load_score,
            "daily_stress": point["daily_stress"],
            "hard_on_red":  score < 30 and point["daily_stress"] > max(point["ctl"], 20.0),
        })
    return out
