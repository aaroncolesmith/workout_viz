"""
Insight Service — template-based post-workout analysis.

Generates structured insights for a single activity by combining:
  - PR detection results (from pr_events table)
  - Fastest segment ranking across all efforts of same type
  - HR efficiency vs similar-pace workouts
  - Split quality (even / negative / positive split)
  - Pace trend context (vs 8-week rolling average)
  - Volume context (longest/shortest effort recently)

All analysis is rule-based — no ML or LLM needed.  The output is a
structured dict with named sections so the frontend can render each
piece independently and handle missing data gracefully.

Schema returned by get_insights():
    {
      "headline":           str | None,   # Most notable thing about this workout
      "pr":                 dict | None,  # PR details if this is a PR
      "segment_ranking":    dict | None,  # e.g. "3rd fastest 10K"
      "hr_efficiency":      dict | None,  # HR vs similar-pace workouts
      "split_quality":      dict | None,  # Even / negative / positive split
      "pace_trend":         dict | None,  # Trending faster or slower
      "volume_context":     dict | None,  # Longest/shortest in recent window
    }
"""

import logging
from typing import Optional
from backend.services.database import get_conn

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt_pace(pace_min: float) -> str:
    """Convert decimal min/mile to 'M:SS/mi'."""
    minutes = int(pace_min)
    seconds = int(round((pace_min - minutes) * 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}/mi"


def _fmt_time(seconds: float) -> str:
    t = int(seconds)
    h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{['st','nd','rd'][n % 10 - 1] if n % 10 in (1,2,3) else 'th'}"


# ── individual insight generators ────────────────────────────────────────────

def _pr_insight(activity_id: int, conn) -> Optional[dict]:
    """Return PR details if this activity has any registered PR events."""
    rows = conn.execute("""
        SELECT distance_label, time_str, pace_str, previous_best_seconds, time_seconds
        FROM   pr_events
        WHERE  activity_id = ?
        ORDER  BY distance_miles DESC
    """, (activity_id,)).fetchall()

    if not rows:
        return None

    # Pick the most significant PR (longest distance)
    best = rows[0]
    prev = best["previous_best_seconds"]
    improvement = None
    if prev:
        delta_s = prev - best["time_seconds"]
        improvement = f"{_fmt_time(abs(delta_s))} faster than previous best"

    all_labels = [r["distance_label"] for r in rows]
    return {
        "distance_label": best["distance_label"],
        "time_str":        best["time_str"],
        "pace_str":        best["pace_str"],
        "improvement":     improvement,
        "all_distances":   all_labels,
        "is_first_effort": prev is None,
    }


def _segment_ranking_insight(activity_id: int, activity_type: str, conn) -> Optional[dict]:
    """
    For each standard distance, find this activity's ranking among all
    summaries of the same activity type.  Return the ranking for the
    most impressive distance (largest distance with top-10 finish).
    """
    # Get this activity's summaries
    my_rows = conn.execute("""
        SELECT distance_miles, fastest_time_seconds
        FROM   summaries
        WHERE  activity_id = ?
    """, (activity_id,)).fetchall()

    if not my_rows:
        return None

    label_map = {
        1.0:   "1 Mile",   2.0:  "2 Miles",  3.107: "5K",
        5.0:   "5 Miles",  6.214: "10K",      13.1:  "Half Marathon",
        26.2:  "Marathon",
    }

    best_result = None
    best_dist   = 0.0

    for row in my_rows:
        dist  = float(row["distance_miles"])
        my_t  = float(row["fastest_time_seconds"])

        # Rank: count how many activities of same type have a faster time
        rank_row = conn.execute("""
            SELECT COUNT(*) as faster_count
            FROM   summaries s
            JOIN   activities a ON a.id = s.activity_id
            WHERE  a.type = ?
              AND  s.distance_miles = ?
              AND  s.fastest_time_seconds < ?
        """, (activity_type, dist, my_t)).fetchone()

        rank = int(rank_row["faster_count"]) + 1  # 1-indexed

        # Total count for this distance
        total_row = conn.execute("""
            SELECT COUNT(*) as total
            FROM   summaries s
            JOIN   activities a ON a.id = s.activity_id
            WHERE  a.type = ?
              AND  s.distance_miles = ?
        """, (activity_type, dist)).fetchone()
        total = int(total_row["total"])

        # Only keep top-20 results for display; prefer longer distances
        if rank <= 20 and dist > best_dist:
            label = min(label_map, key=lambda k: abs(k - dist))
            label = label_map[label]
            best_dist   = dist
            best_result = {
                "distance_label": label,
                "rank":           rank,
                "total":          total,
                "ordinal":        _ordinal(rank),
                "time_str":       _fmt_time(my_t),
                "pace_per_mile":  my_t / dist / 60,
            }

    return best_result


def _hr_efficiency_insight(activity_id: int, conn) -> Optional[dict]:
    """
    Compare this activity's avg HR against similar-pace activities.
    Returns a delta (bpm) indicating whether HR was better or worse.
    Only meaningful for activities with HR data.
    """
    act = conn.execute("""
        SELECT average_heartrate, pace, type, distance_miles
        FROM   activities WHERE id = ?
    """, (activity_id,)).fetchone()

    if not act or not act["average_heartrate"] or not act["pace"]:
        return None

    my_hr   = float(act["average_heartrate"])
    my_pace = float(act["pace"])
    act_type = act["type"]

    # Activities of same type with pace within ±0.5 min/mi and has HR
    # Exclude current activity; limit to recent 50 for relevance
    rows = conn.execute("""
        SELECT average_heartrate, date
        FROM   activities
        WHERE  type = ?
          AND  id   != ?
          AND  has_heartrate = 1
          AND  average_heartrate > 0
          AND  pace BETWEEN ? AND ?
        ORDER  BY date DESC
        LIMIT  50
    """, (act_type, activity_id, my_pace - 0.5, my_pace + 0.5)).fetchall()

    if len(rows) < 3:
        return None

    avg_similar_hr = sum(float(r["average_heartrate"]) for r in rows) / len(rows)
    delta = my_hr - avg_similar_hr  # negative = better (lower HR at same pace)
    sample_size = len(rows)

    if abs(delta) < 2:
        return None  # Not meaningful enough to surface

    return {
        "my_hr":           round(my_hr, 1),
        "avg_similar_hr":  round(avg_similar_hr, 1),
        "delta_bpm":       round(delta, 1),
        "better":          delta < 0,
        "sample_size":     sample_size,
        "pace_str":        _fmt_pace(my_pace),
    }


def _split_quality_insight(activity_id: int, conn) -> Optional[dict]:
    """
    Compare first-half vs second-half split pace.
    Returns split type: negative (faster finish), positive (slow fade), even.
    """
    splits = conn.execute("""
        SELECT split_number, time_seconds, total_distance_miles
        FROM   splits
        WHERE  activity_id = ?
        ORDER  BY split_number ASC
    """, (activity_id,)).fetchall()

    if len(splits) < 6:  # Need at least 0.6 miles of data
        return None

    total = len(splits)
    half  = total // 2
    first_half  = splits[:half]
    second_half = splits[half:]

    first_avg  = sum(float(s["time_seconds"]) for s in first_half)  / len(first_half)
    second_avg = sum(float(s["time_seconds"]) for s in second_half) / len(second_half)

    # Convert to pace per mile (each split is 0.1 mile)
    first_pace_min  = (first_avg  / 60) * 10  # time for 0.1 mi → multiply by 10 for 1 mi
    second_pace_min = (second_avg / 60) * 10

    delta_s = second_avg - first_avg  # positive = slowing down, negative = speeding up
    delta_pace = second_pace_min - first_pace_min

    if abs(delta_s) < 3:  # < 3 sec per split = effectively even
        split_type = "even"
    elif delta_s < 0:
        split_type = "negative"  # faster in second half
    else:
        split_type = "positive"  # slower in second half

    return {
        "split_type":       split_type,
        "first_pace_str":   _fmt_pace(first_pace_min),
        "second_pace_str":  _fmt_pace(second_pace_min),
        "delta_seconds":    round(abs(delta_s), 1),
        "delta_pace":       round(abs(delta_pace), 2),
        "total_splits":     total,
    }


def _pace_trend_insight(activity_id: int, activity_type: str, conn) -> Optional[dict]:
    """
    Compare this activity's pace vs the 8-week rolling average for same type.
    Only for activities with non-trivial distance (>= 1 mile).
    """
    act = conn.execute("""
        SELECT pace, distance_miles, date FROM activities WHERE id = ?
    """, (activity_id,)).fetchone()

    if not act or not act["pace"] or float(act["pace"]) <= 0:
        return None
    if not act["distance_miles"] or float(act["distance_miles"]) < 1.0:
        return None

    my_pace = float(act["pace"])
    act_date = act["date"]

    # 8-week average pace for same activity type, excluding current activity
    rows = conn.execute("""
        SELECT pace, date
        FROM   activities
        WHERE  type  = ?
          AND  id   != ?
          AND  date < ?
          AND  pace > 0
          AND  distance_miles >= 1.0
          AND  date >= DATE(?, '-56 days')
        ORDER  BY date DESC
        LIMIT  30
    """, (activity_type, activity_id, act_date, act_date)).fetchall()

    if len(rows) < 4:
        return None

    avg_pace = sum(float(r["pace"]) for r in rows) / len(rows)
    delta    = my_pace - avg_pace  # negative = faster than average (better)

    if abs(delta) < 0.05:  # < 3 seconds per mile = not meaningful
        return None

    return {
        "my_pace_str":   _fmt_pace(my_pace),
        "avg_pace_str":  _fmt_pace(avg_pace),
        "delta_min":     round(abs(delta), 2),
        "delta_str":     f"{int(abs(delta)*60)}s/mi",
        "faster":        delta < 0,
        "sample_size":   len(rows),
        "window_weeks":  8,
    }


def _volume_context_insight(activity_id: int, activity_type: str, conn) -> Optional[dict]:
    """
    Is this the longest / shortest run in the past 6 weeks?
    """
    act = conn.execute("""
        SELECT distance_miles, date FROM activities WHERE id = ?
    """, (activity_id,)).fetchone()

    if not act or not act["distance_miles"]:
        return None

    my_dist  = float(act["distance_miles"])
    act_date = act["date"]

    rows = conn.execute("""
        SELECT distance_miles
        FROM   activities
        WHERE  type  = ?
          AND  id   != ?
          AND  date >= DATE(?, '-42 days')
          AND  distance_miles > 0.5
    """, (activity_type, activity_id, act_date)).fetchall()

    if len(rows) < 3:
        return None

    dists     = [float(r["distance_miles"]) for r in rows]
    max_dist  = max(dists)
    min_dist  = min(dists)

    if my_dist >= max_dist:
        return {"context": "longest", "distance": round(my_dist, 1), "window_weeks": 6}
    if my_dist <= min_dist:
        return {"context": "shortest", "distance": round(my_dist, 1), "window_weeks": 6}
    return None


# ── main entry point ─────────────────────────────────────────────────────────

def get_insights(activity_id: int) -> dict:
    """
    Generate structured insights for a single activity.
    Returns a dict with named sections; any section may be None if
    there is not enough data to generate a meaningful insight.
    """
    conn = get_conn()

    act = conn.execute(
        "SELECT id, type, name FROM activities WHERE id = ?", (activity_id,)
    ).fetchone()

    if not act:
        return {}

    act_type = act["type"] or "Run"

    pr              = _pr_insight(activity_id, conn)
    segment_ranking = _segment_ranking_insight(activity_id, act_type, conn)
    hr_efficiency   = _hr_efficiency_insight(activity_id, conn)
    split_quality   = _split_quality_insight(activity_id, conn)
    pace_trend      = _pace_trend_insight(activity_id, act_type, conn)
    volume_context  = _volume_context_insight(activity_id, act_type, conn)

    # Build headline: pick the most notable insight in priority order
    headline = None
    if pr:
        if pr.get("is_first_effort"):
            headline = f"First {pr['distance_label']} effort recorded — {pr['time_str']} ({pr['pace_str']})"
        else:
            headline = f"New {pr['distance_label']} PR: {pr['time_str']} ({pr['pace_str']})"
            if pr.get("improvement"):
                headline += f" — {pr['improvement']}"
    elif segment_ranking and segment_ranking["rank"] <= 5:
        r = segment_ranking
        headline = f"{r['ordinal']} fastest {r['distance_label']} of {r['total']} efforts — {r['time_str']}"
    elif pace_trend and pace_trend["faster"]:
        t = pace_trend
        headline = f"Running {t['delta_str']} faster than your {t['window_weeks']}-week average"
    elif hr_efficiency and hr_efficiency["better"]:
        h = hr_efficiency
        headline = f"HR {abs(h['delta_bpm']):.0f}bpm lower than similar-pace workouts — aerobic efficiency up"
    elif volume_context and volume_context["context"] == "longest":
        v = volume_context
        headline = f"Longest {act_type.lower()} in {v['window_weeks']} weeks — {v['distance']:.1f} mi"

    return {
        "headline":        headline,
        "pr":              pr,
        "segment_ranking": segment_ranking,
        "hr_efficiency":   hr_efficiency,
        "split_quality":   split_quality,
        "pace_trend":      pace_trend,
        "volume_context":  volume_context,
    }
