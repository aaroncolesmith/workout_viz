"""
Race predictor — Riegel-formula time predictions adjusted for current form.

For each target race distance, finds the best recent effort at the closest
available source distance, applies Riegel's endurance formula, and applies a
small form adjustment based on the 4-week CTL trend.

Riegel formula: T2 = T1 * (D2 / D1) ^ 1.06
"""
import math
import logging
from datetime import date, timedelta
from typing import Optional
from backend.services.database import get_conn

logger = logging.getLogger(__name__)

# ── Standard distances ───────────────────────────────────────────────────────

# Distances stored in the summaries table (miles)
SOURCE_DISTANCES = [
    (1.0,   "1 Mile"),
    (2.0,   "2 Miles"),
    (3.107, "5K"),
    (5.0,   "5 Miles"),
    (6.214, "10K"),
    (13.1,  "Half Marathon"),
    (26.2,  "Marathon"),
]

# Distances we predict for
TARGET_DISTANCES = [
    (3.107, "5K"),
    (6.214, "10K"),
    (13.1,  "Half Marathon"),
    (26.2,  "Marathon"),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _riegel(t1_sec: float, d1_miles: float, d2_miles: float) -> float:
    """Apply Riegel's endurance formula."""
    return t1_sec * (d2_miles / d1_miles) ** 1.06


def _fmt_time(seconds: float) -> str:
    seconds = round(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_pace(time_sec: float, distance_miles: float) -> str:
    pace_sec = time_sec / distance_miles
    m = int(pace_sec // 60)
    s = int(pace_sec % 60)
    return f"{m}:{s:02d}/mi"


def _confidence(source_miles: float, target_miles: float, days_old: int) -> str:
    """
    Rate prediction confidence based on how close the source distance is
    to the target and how recent the effort was.
    """
    ratio = source_miles / target_miles
    if ratio >= 0.6 and days_old <= 60:
        return "high"
    if ratio >= 0.35 and days_old <= 90:
        return "medium"
    return "low"


def _get_ctl_trend(conn, days: int = 28) -> Optional[float]:
    """
    Returns the change in CTL over the last `days` days (positive = building fitness).
    Uses a simple linear regression slope on daily load.
    """
    try:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT date, moving_time_min, average_heartrate
            FROM activities
            WHERE date >= ? AND average_heartrate IS NOT NULL AND moving_time_min > 0
            ORDER BY date ASC
        """, (cutoff,)).fetchall()

        if len(rows) < 3:
            return None

        # Rough weekly mileage trend as a proxy (avoids importing fitness_service)
        first_week = [r for r in rows if r[0] <= (date.today() - timedelta(days=days - 7)).isoformat()]
        last_week  = [r for r in rows if r[0] >= (date.today() - timedelta(days=7)).isoformat()]

        def _weekly_load(week_rows):
            return sum((r[1] or 0) for r in week_rows)

        if not first_week or not last_week:
            return None

        trend = _weekly_load(last_week) - _weekly_load(first_week)
        return trend  # positive = increasing load
    except Exception as e:
        logger.warning(f"CTL trend computation failed: {e}")
        return None


# ── Main entry point ─────────────────────────────────────────────────────────

def get_race_predictions(activity_type: str = "Run", days: int = 90) -> list:
    """
    Return race time predictions for standard distances.

    For each target distance:
      1. Find the best effort at every source distance within `days`.
      2. Choose the source closest to target (highest ratio ≤ 1.0).
      3. Apply Riegel formula.
      4. Apply a small form adjustment (±2%) based on recent load trend.
      5. Return prediction with confidence, source attribution, and range.
    """
    conn = get_conn()
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    # Fetch all best efforts within the window, grouped by distance
    rows = conn.execute("""
        SELECT
            s.distance_miles,
            MIN(s.fastest_time_seconds) AS best_time,
            a.id                        AS activity_id,
            a.name                      AS activity_name,
            a.date
        FROM summaries s
        JOIN activities a ON a.id = s.activity_id
        WHERE a.type = ?
          AND a.date >= ?
          AND s.fastest_time_seconds > 0
        GROUP BY s.distance_miles
        ORDER BY s.distance_miles ASC
    """, (activity_type, cutoff)).fetchall()

    # Build lookup: distance_miles -> {time, activity_id, name, date}
    best_by_dist: dict = {}
    for r in rows:
        d_mi = round(float(r[0]), 3)
        # Keep the fastest if there happen to be multiple rows for the same distance
        if d_mi not in best_by_dist or float(r[1]) < best_by_dist[d_mi]["time_sec"]:
            best_by_dist[d_mi] = {
                "time_sec":    float(r[1]),
                "activity_id": r[2],
                "name":        r[3],
                "date":        r[4],
            }

    if not best_by_dist:
        return []

    ctl_trend = _get_ctl_trend(conn)
    # Form multiplier: ±2% maximum, proportional to trend magnitude
    form_multiplier = 1.0
    if ctl_trend is not None:
        # Clamp to ±2%
        adjustment = max(-0.02, min(0.02, ctl_trend / 5000.0))
        form_multiplier = 1.0 - adjustment  # positive trend → faster (smaller time)

    today_str = date.today().isoformat()
    predictions = []

    for target_miles, target_label in TARGET_DISTANCES:
        # Find the best source: highest distance that is ≤ target
        # (predicting "up" in distance is more reliable than predicting down)
        candidates = [
            (d, info) for d, info in best_by_dist.items()
            if d <= target_miles * 1.05  # allow slight overshoot (e.g. 13.2 for HM)
        ]
        if not candidates:
            continue

        # Prefer sources closest to target (highest d)
        candidates.sort(key=lambda x: x[0], reverse=True)
        source_miles, source = candidates[0]

        # Riegel prediction
        raw_sec = _riegel(source["time_sec"], source_miles, target_miles)
        adjusted_sec = raw_sec * form_multiplier

        # Confidence interval ±3% of adjusted time
        low_sec  = adjusted_sec * 0.97
        high_sec = adjusted_sec * 1.03

        days_old = max(0, (
            date.fromisoformat(today_str) - date.fromisoformat(source["date"])
        ).days)

        confidence = _confidence(source_miles, target_miles, days_old)

        # Find the label for the source distance
        source_label = next(
            (lbl for d, lbl in SOURCE_DISTANCES if abs(d - source_miles) < 0.05),
            f"{source_miles:.1f} mi"
        )

        predictions.append({
            "target_distance_miles": target_miles,
            "target_label":          target_label,
            "predicted_time_sec":    round(adjusted_sec, 1),
            "predicted_time_str":    _fmt_time(adjusted_sec),
            "predicted_pace_str":    _fmt_pace(adjusted_sec, target_miles),
            "low_time_str":          _fmt_time(low_sec),
            "high_time_str":         _fmt_time(high_sec),
            "confidence":            confidence,
            "form_multiplier":       round(form_multiplier, 4),
            "source": {
                "distance_miles": source_miles,
                "distance_label": source_label,
                "time_sec":       source["time_sec"],
                "time_str":       _fmt_time(source["time_sec"]),
                "pace_str":       _fmt_pace(source["time_sec"], source_miles),
                "activity_id":    source["activity_id"],
                "activity_name":  source["name"],
                "date":           source["date"],
                "days_old":       days_old,
            },
        })

    return predictions
