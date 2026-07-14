"""
Correlation Service (Phase D) — connecting body signals to performance.

COR-1 — Effect analyses:
    For each factor (sleep, morning HRV/RHR vs baseline, rest days), split
    the user's runs into two cohorts and compare **effort-adjusted pace**
    (pace normalised to the user's median HR — pace × hr/ref_hr, i.e. what
    the run would have cost at a reference effort).  A finding is surfaced
    only when both cohorts have n ≥ 8, the Welch t-statistic clears 2.0
    (≈ p < .05), and the effect is ≥ 3 s/mi.  Direction is taken from the
    data, never assumed — if short sleep genuinely runs faster for this
    user, that's what the card says.

COR-2 — Efficiency trend:
    Efficiency Factor (EF) per run = meters-per-minute / avg HR, the single
    best "am I actually getting fitter?" signal: it rises when the same
    speed costs fewer beats, independent of how hard individual days felt.
    Served with a 42-day rolling mean for the trend line.

    Aerobic decoupling per run = how much the pace:HR ratio decays from the
    first half to the second half (positive % = fading).  Computed from the
    activity's splits, so it works at any split grain.  < 5% on a long run
    is the classic aerobic-base benchmark.

Rule-based and explainable, like everything else — no ML.
House rules: explicit conn= injection; cached by the caller.
"""
import logging
import math
from datetime import date as _date, datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

METERS_PER_MILE = 1609.344

_EF_TYPES = ("Run", "TrailRun", "VirtualRun")
_MIN_EF_DISTANCE_MI = 2.0       # too short → HR lag dominates
_MIN_DECOUPLING_MIN = 45.0      # decoupling only means something on longer efforts
_ROLLING_DAYS = 42


def _ef(pace_min_mi: float, avg_hr: float) -> Optional[float]:
    """Efficiency Factor: meters per minute per heartbeat-per-minute."""
    if not pace_min_mi or pace_min_mi <= 0 or not avg_hr or avg_hr <= 0:
        return None
    speed_m_per_min = METERS_PER_MILE / pace_min_mi
    return speed_m_per_min / avg_hr


def _decoupling(splits: List[dict]) -> Optional[float]:
    """
    First-half vs second-half EF decay in percent (positive = fading).
    Grain-agnostic: halves are split by cumulative distance, not row count.
    """
    rows = sorted(splits, key=lambda s: float(s.get("split_number") or 0))
    if len(rows) < 4:
        return None

    total_dist = float(rows[-1].get("total_distance_miles") or 0)
    if total_dist <= 0:
        return None

    halves = ([], [])   # (dist_mi, time_s, hr) tuples per half
    prev_mile = 0.0
    for r in rows:
        mile = float(r.get("total_distance_miles") or 0)
        hr = r.get("avg_heartrate")
        seg = (mile - prev_mile, float(r.get("time_seconds") or 0),
               float(hr) if hr else None)
        halves[0 if mile <= total_dist / 2 else 1].append(seg)
        prev_mile = mile

    efs = []
    for segs in halves:
        dist = sum(s[0] for s in segs)
        time_min = sum(s[1] for s in segs) / 60
        hr_segs = [s for s in segs if s[2]]
        if dist <= 0 or time_min <= 0 or not hr_segs:
            return None
        # Distance-weighted HR so a fine-grain half isn't skewed by short rows
        hr = sum(s[2] * s[0] for s in hr_segs) / sum(s[0] for s in hr_segs)
        ef = _ef(time_min / dist, hr)
        if not ef:
            return None
        efs.append(ef)

    return round((efs[0] - efs[1]) / efs[0] * 100, 1)


def get_efficiency_trend(days: int = 365, activity_type: str = "Run", *, conn) -> dict:
    """
    EF per qualifying run + a rolling-mean trend line, plus decoupling for
    runs long enough for it to mean anything.
    """
    types = _EF_TYPES if activity_type == "Run" else (activity_type,)
    cutoff = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(f"""
        SELECT id, date, name, distance_miles, pace, average_heartrate, moving_time_min
        FROM   activities
        WHERE  type IN ({','.join(['?'] * len(types))})
          AND  date >= ?
          AND  has_heartrate = 1
          AND  distance_miles >= ?
          AND  pace > 0
        ORDER  BY date ASC
    """, (*types, cutoff, _MIN_EF_DISTANCE_MI)).fetchall()

    points = []
    for r in rows:
        ef = _ef(float(r["pace"]), float(r["average_heartrate"]))
        if not ef:
            continue
        point = {
            "activity_id": r["id"],
            "date":        r["date"],
            "name":        r["name"],
            "ef":          round(ef, 3),
            "pace":        round(float(r["pace"]), 3),
            "avg_hr":      round(float(r["average_heartrate"]), 1),
            "decoupling":  None,
        }
        if float(r["moving_time_min"] or 0) >= _MIN_DECOUPLING_MIN:
            splits = conn.execute(
                "SELECT split_number, time_seconds, total_distance_miles, avg_heartrate "
                "FROM splits WHERE activity_id = ?", (r["id"],)
            ).fetchall()
            point["decoupling"] = _decoupling([dict(s) for s in splits])
        points.append(point)

    # Rolling EF: mean over the trailing _ROLLING_DAYS window per point
    by_date = [(datetime.fromisoformat(p["date"]), p["ef"]) for p in points]
    for i, p in enumerate(points):
        d = by_date[i][0]
        window = [ef for (dd, ef) in by_date if timedelta(0) <= d - dd <= timedelta(days=_ROLLING_DAYS)]
        p["ef_rolling"] = round(sum(window) / len(window), 3)

    # Plain-language trend verdict: latest rolling vs ~6 weeks earlier
    verdict = None
    if len(points) >= 5:
        latest = points[-1]
        anchor_date = by_date[-1][0] - timedelta(days=_ROLLING_DAYS)
        earlier = [p for p, (dd, _) in zip(points, by_date) if dd <= anchor_date]
        if earlier:
            prev = earlier[-1]["ef_rolling"]
            delta_pct = (latest["ef_rolling"] - prev) / prev * 100
            if delta_pct > 1.5:
                verdict = (f"Efficiency up {delta_pct:.1f}% over ~6 weeks — "
                           "the same heart rate is buying you more speed.")
            elif delta_pct < -1.5:
                verdict = (f"Efficiency down {abs(delta_pct):.1f}% over ~6 weeks — "
                           "often fatigue, heat, or a training gap.")
            else:
                verdict = "Efficiency is holding steady over the last ~6 weeks."

    return {"points": points, "verdict": verdict,
            "rolling_days": _ROLLING_DAYS, "activity_type": activity_type}


# ── COR-1: effect analyses ────────────────────────────────────────────────────

_MIN_COHORT_N = 8
_T_THRESHOLD = 2.0          # ≈ p < .05 for these sample sizes
_T_HIGH = 2.6
_MIN_EFFECT_SEC_MI = 3.0
_SLEEP_SPLIT_HOURS = 7.0


def _welch_t(a: List[float], b: List[float]) -> Optional[float]:
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    denom = math.sqrt(va / na + vb / nb)
    return (ma - mb) / denom if denom > 0 else None


def _fmt_pace(p: float) -> str:
    m = int(p)
    s = int(round((p - m) * 60))
    if s == 60:
        m, s = m + 1, 0
    return f"{m}:{s:02d}/mi"


def get_effect_findings(days: int = 365, *, conn) -> dict:
    """
    COR-1 — which conditions actually change this user's running?
    Returns only findings that clear the sample-size / significance /
    effect-size bars, each with the underlying cohort stats so the UI can
    always show its work.
    """
    from backend.services.health_metrics_service import _load_series, _window_mean

    cutoff = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    runs = [dict(r) for r in conn.execute(f"""
        SELECT id, date, pace, average_heartrate
        FROM   activities
        WHERE  type IN ({','.join(['?'] * len(_EF_TYPES))})
          AND  date >= ? AND has_heartrate = 1
          AND  pace > 0 AND distance_miles >= ?
        ORDER  BY date ASC
    """, (*_EF_TYPES, cutoff, _MIN_EF_DISTANCE_MI)).fetchall()]

    if len(runs) < 2 * _MIN_COHORT_N:
        return {"findings": [], "runs_analyzed": len(runs)}

    hrs = sorted(float(r["average_heartrate"]) for r in runs)
    ref_hr = hrs[len(hrs) // 2]
    for r in runs:
        # Effort-adjusted pace: what this pace would cost at the reference HR
        r["adj_pace"] = float(r["pace"]) * float(r["average_heartrate"]) / ref_hr
        r["day"] = _date.fromisoformat(r["date"])

    series = {m: _load_series(conn, m)
              for m in ("sleep_asleep", "hrv_sdnn", "resting_heartrate")}

    # All activity dates, for the rest-days factor
    all_days = sorted({_date.fromisoformat(row["date"])
                       for row in conn.execute(
                           "SELECT DISTINCT date FROM activities WHERE date IS NOT NULL"
                       ).fetchall()})

    def _rest_days(d: _date) -> Optional[int]:
        prev = [x for x in all_days if x < d]
        return (d - prev[-1]).days if prev else None

    def _baseline_dev(metric: str, d: _date) -> Optional[float]:
        val = series[metric].get(d)
        if val is None:
            return None
        base = _window_mean(series[metric], d - timedelta(days=1), 30)
        return (val - base) if base else None

    # factor → (cohort-A test, label-A phrase, label-B phrase)
    def _sleep_side(r):
        v = series["sleep_asleep"].get(r["day"])
        return None if v is None else v >= _SLEEP_SPLIT_HOURS

    def _hrv_side(r):
        dev = _baseline_dev("hrv_sdnn", r["day"])
        return None if dev is None else dev >= 0

    def _rhr_side(r):
        dev = _baseline_dev("resting_heartrate", r["day"])
        return None if dev is None else dev <= 0

    def _rest_side(r):
        g = _rest_days(r["day"])
        return None if g is None else g >= 2

    factors = [
        ("sleep", _sleep_side, "after 7+ hours of sleep", "after nights under 7 hours"),
        ("hrv", _hrv_side, "when morning HRV is at or above baseline", "when morning HRV is below baseline"),
        ("rhr", _rhr_side, "when resting HR is at or below baseline", "when resting HR is elevated"),
        ("rest", _rest_side, "after 2+ rest days", "on 0–1 days of rest"),
    ]

    findings = []
    for key, side_fn, phrase_a, phrase_b in factors:
        a = [r["adj_pace"] for r in runs if side_fn(r) is True]
        b = [r["adj_pace"] for r in runs if side_fn(r) is False]
        if len(a) < _MIN_COHORT_N or len(b) < _MIN_COHORT_N:
            continue
        t = _welch_t(a, b)
        if t is None or abs(t) < _T_THRESHOLD:
            continue
        mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
        delta_sec = abs(mean_a - mean_b) * 60
        if delta_sec < _MIN_EFFECT_SEC_MI:
            continue

        a_faster = mean_a < mean_b
        phrase = phrase_a if a_faster else phrase_b
        n = len(a) + len(b)
        findings.append({
            "factor": key,
            "headline": (f"Across {n} runs, you average {delta_sec:.0f} s/mi faster "
                         f"(effort-adjusted) {phrase}."),
            "delta_sec_mi": round(delta_sec, 1),
            "confidence": "high" if abs(t) >= _T_HIGH else "moderate",
            "cohorts": [
                {"label": phrase_a, "n": len(a), "adj_pace": round(mean_a, 3),
                 "adj_pace_str": _fmt_pace(mean_a)},
                {"label": phrase_b, "n": len(b), "adj_pace": round(mean_b, 3),
                 "adj_pace_str": _fmt_pace(mean_b)},
            ],
        })

    findings.sort(key=lambda f: f["delta_sec_mi"], reverse=True)
    return {"findings": findings, "runs_analyzed": len(runs), "ref_hr": round(ref_hr, 1)}
