"""
Comparison Service (CMP-1) — the post-workout verdict.

Answers, with zero configuration: *was I faster? was it harder? where does
this rank?*  The comparison cohort is selected automatically, best evidence
first:

  1. same route      — activities sharing this one's route cluster
                       (gold standard: same course, true apples-to-apples);
  2. similar         — similarity_service matches above a score threshold
                       (which already includes a GPS route-match factor);
  3. distance band   — same type within ±15% distance.

A single previous attempt is still a valid cohort ("your only other run on
this route").  When no cohort exists at all, the response still carries the
relative-effort score (CMP-2), which works for any activity type.

Verdict text is generated here — the ActivityDetail hero card, the insight
headline, and (later) the post-sync push notification all reuse it so the
product speaks with one voice.

House rules: explicit data_service= injection, results cached in the
per-user analytics cache (flushed on every write).
"""
import logging
from typing import List, Optional

from backend.services.fitness_service import get_relative_effort, _ordinal
from backend.services.similarity_service import find_similar_activities

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.75
DISTANCE_BAND = 0.15       # ±15%
# Noise floors: differences smaller than these read as "the same effort".
_NOISE_PACE_MIN = 0.05     # min/mi ≈ 3 s/mi
_NOISE_HR_BPM = 2.0

_MEMBER_COLS = "a.id, a.name, a.date, a.moving_time_min, a.pace, a.average_heartrate, a.distance_miles"


def _sport_noun(activity_type: str) -> str:
    return {
        "Run": "run", "TrailRun": "run", "VirtualRun": "run",
        "Ride": "ride", "VirtualRide": "ride",
        "Swim": "swim", "Walk": "walk", "Hike": "hike",
    }.get(activity_type, "workout")


# ── cohort selection ──────────────────────────────────────────────────────────

def _route_cohort(activity_id: int, activity_type: str, conn):
    row = conn.execute("""
        SELECT r.id AS route_id, r.name
        FROM   route_activities ra JOIN routes r ON r.id = ra.route_id
        WHERE  ra.activity_id = ?
        LIMIT  1
    """, (activity_id,)).fetchone()
    if not row:
        return None
    members = [dict(m) for m in conn.execute(f"""
        SELECT {_MEMBER_COLS}
        FROM   route_activities ra JOIN activities a ON a.id = ra.activity_id
        WHERE  ra.route_id = ? AND ra.activity_id != ? AND a.moving_time_min > 0
        ORDER  BY a.date
    """, (row["route_id"], activity_id)).fetchall()]
    if not members:
        return None
    noun = _sport_noun(activity_type)
    return {
        "kind": "route",
        "label": f"{len(members)} previous {noun}{'s' if len(members) != 1 else ''} on {row['name']}",
        "place": row["name"],
        "route_id": row["route_id"],
        "members": members,
        "rank_metric": "time",   # same course → absolute time is comparable
    }


def _similar_cohort(activity_id: int, activity_type: str, data_service):
    try:
        results = find_similar_activities(activity_id, top_n=15, data_service=data_service)
    except Exception as e:
        logger.warning(f"similarity lookup failed for {activity_id}: {e}")
        return None
    members = [
        {
            "id": r["activity"]["id"],
            "name": r["activity"]["name"],
            "date": r["activity"]["date"],
            "moving_time_min": r["activity"]["moving_time_min"],
            "pace": r["activity"]["pace"] or None,
            "average_heartrate": r["activity"]["average_heartrate"],
            "distance_miles": r["activity"]["distance_miles"],
        }
        for r in results
        if r["similarity_score"] >= SIMILARITY_THRESHOLD
        and (r["activity"]["moving_time_min"] or 0) > 0
    ]
    if not members:
        return None
    members.sort(key=lambda m: m["date"] or "")
    noun = _sport_noun(activity_type)
    return {
        "kind": "similar",
        "label": f"{len(members)} similar {noun}{'s' if len(members) != 1 else ''}",
        "place": None,
        "route_id": None,
        "members": members,
        "rank_metric": "pace",
    }


def _distance_cohort(activity: dict, conn):
    dist = float(activity.get("distance_miles") or 0.0)
    if dist <= 0.1:
        return None
    members = [dict(m) for m in conn.execute(f"""
        SELECT {_MEMBER_COLS}
        FROM   activities a
        WHERE  a.type = ? AND a.id != ?
          AND  a.distance_miles BETWEEN ? AND ?
          AND  a.moving_time_min > 0
        ORDER  BY a.date DESC
        LIMIT  50
    """, (activity["type"], activity["id"],
          dist * (1 - DISTANCE_BAND), dist * (1 + DISTANCE_BAND))).fetchall()]
    if not members:
        return None
    members.sort(key=lambda m: m["date"] or "")
    noun = _sport_noun(activity["type"])
    return {
        "kind": "distance",
        "label": f"{len(members)} {noun}{'s' if len(members) != 1 else ''} around {dist:.1f} mi",
        "place": None,
        "route_id": None,
        "members": members,
        "rank_metric": "pace",
    }


# ── analysis ──────────────────────────────────────────────────────────────────

def _mean(vals: List[float]) -> Optional[float]:
    vals = [v for v in vals if v]
    return sum(vals) / len(vals) if vals else None


def _rank(activity: dict, members: List[dict], metric: str):
    """1-based rank among cohort+self; lower time/pace is better."""
    key = "moving_time_min" if metric == "time" else "pace"
    mine = activity.get(key)
    if not mine:
        return None, None
    others = [m.get(key) for m in members if m.get(key)]
    better = sum(1 for v in others if v < mine)
    return better + 1, len(others) + 1


def _efficiency(pace_delta: Optional[float], hr_delta: Optional[float]) -> Optional[str]:
    """2×2 of pace vs HR deltas (each vs cohort average), with noise floors."""
    if pace_delta is None:
        return None
    faster = pace_delta < -_NOISE_PACE_MIN
    slower = pace_delta > _NOISE_PACE_MIN
    if hr_delta is None:
        return "faster" if faster else "slower" if slower else "consistent"
    hr_up = hr_delta > _NOISE_HR_BPM
    hr_down = hr_delta < -_NOISE_HR_BPM
    if faster:
        return "pushed" if hr_up else "breakthrough"   # faster at same-or-lower HR
    if slower:
        return "tough" if hr_up else "easy_day" if hr_down else "slower"
    if hr_down:
        return "easier"       # same pace, less effort — efficiency gain
    if hr_up:
        return "strained"     # same pace cost more today
    return "consistent"


_EFFICIENCY_PHRASE = {
    "breakthrough": "faster at a lower heart rate — real fitness gains",
    "pushed":       "faster, but it cost more effort",
    "easier":       "your usual pace at a lower heart rate — efficiency is improving",
    "strained":     "your usual pace took a higher heart rate — watch for fatigue",
    "easy_day":     "an easier day: slower and lower effort",
    "tough":        "slower at a higher heart rate — likely a tough day",
    "faster":       "faster than your average",
    "slower":       "a bit slower than your average",
    "consistent":   "right in line with your typical effort",
}


def _verdict(activity, cohort, rank, rank_of, efficiency, effort) -> Optional[str]:
    if cohort is None:
        if effort:
            return (f"No comparable {_sport_noun(activity.get('type', ''))}s yet — "
                    f"but this was your {effort['label']}.")
        return None
    place = f" on {cohort['place']}" if cohort.get("place") else ""
    parts = []
    if rank and rank_of:
        parts.append(f"Your {_ordinal(rank)} fastest of {rank_of}{place}")
    else:
        parts.append(f"Compared with {cohort['label']}{place if not cohort.get('place') else ''}")
    phrase = _EFFICIENCY_PHRASE.get(efficiency or "")
    if phrase:
        parts.append(phrase)
    return " — ".join(parts) + "."


# ── public API ────────────────────────────────────────────────────────────────

def get_comparison(activity_id: int, *, data_service) -> Optional[dict]:
    """Full auto-comparison block for one activity; None if it doesn't exist."""
    cache = data_service.get_analytics_cache()
    cache_key = f"comparison:{activity_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    activity = data_service.get_activity(activity_id)
    if not activity:
        return None
    conn = data_service._conn()

    cohort = (_route_cohort(activity_id, activity.get("type", ""), conn)
              or _similar_cohort(activity_id, activity.get("type", ""), data_service)
              or _distance_cohort(activity, conn))

    effort = get_relative_effort(activity_id, conn=conn)

    rank = rank_of = None
    deltas = None
    efficiency = None
    history: List[dict] = []

    if cohort:
        members = cohort["members"]
        rank, rank_of = _rank(activity, members, cohort["rank_metric"])

        pace_avg = _mean([m.get("pace") for m in members])
        hr_avg = _mean([m.get("average_heartrate") for m in members])
        time_avg = _mean([m.get("moving_time_min") for m in members])
        times = [m.get("moving_time_min") for m in members if m.get("moving_time_min")]
        paces = [m.get("pace") for m in members if m.get("pace")]

        my_pace = activity.get("pace") or None
        my_hr = activity.get("average_heartrate") or None
        my_time = activity.get("moving_time_min") or None

        pace_delta = (my_pace - pace_avg) if my_pace and pace_avg else None
        hr_delta = (my_hr - hr_avg) if my_hr and hr_avg else None
        deltas = {
            "pace_vs_avg_sec_mi": round(pace_delta * 60, 1) if pace_delta is not None else None,
            "pace_vs_best_sec_mi": round((my_pace - min(paces)) * 60, 1) if my_pace and paces else None,
            "hr_vs_avg_bpm": round(hr_delta, 1) if hr_delta is not None else None,
            "time_vs_avg_sec": round((my_time - time_avg) * 60, 1) if my_time and time_avg else None,
            "time_vs_best_sec": round((my_time - min(times)) * 60, 1) if my_time and times else None,
        }
        efficiency = _efficiency(pace_delta, hr_delta)

        history = [
            {
                "activity_id": m["id"],
                "date": m.get("date"),
                "time_seconds": round(m["moving_time_min"] * 60, 1) if m.get("moving_time_min") else None,
                "pace": m.get("pace"),
                "is_current": False,
            }
            for m in members
        ] + [{
            "activity_id": activity_id,
            "date": activity.get("date"),
            "time_seconds": round(activity["moving_time_min"] * 60, 1) if activity.get("moving_time_min") else None,
            "pace": activity.get("pace") or None,
            "is_current": True,
        }]
        history.sort(key=lambda h: h["date"] or "")

    result = {
        "activity_id": activity_id,
        "cohort": {
            "kind": cohort["kind"], "label": cohort["label"],
            "route_id": cohort["route_id"], "size": len(cohort["members"]),
        } if cohort else None,
        "rank": rank,
        "rank_of": rank_of,
        "rank_metric": cohort["rank_metric"] if cohort and rank else None,
        "efficiency": efficiency,
        "verdict": _verdict(activity, cohort, rank, rank_of, efficiency, effort),
        "deltas": deltas,
        "effort": effort,
        "history": history,
    }
    cache.set(cache_key, result)
    return result
