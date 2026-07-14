"""
Weekly Digest (COR-4) — a synthesized narrative of the last 7 days.

Composes from services that already exist (volume from activities,
efficiency verdict from correlation_service, body drift from
health_metrics, best moment from EF ranks, readiness trend) — the digest
invents no numbers of its own, so it can never disagree with the charts.

House rules: explicit conn= injection; cached by the caller.
"""
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def _fmt_hours(hours: float) -> str:
    h = int(hours)
    m = int(round((hours - h) * 60))
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{['st', 'nd', 'rd'][n % 10 - 1] if n % 10 in (1, 2, 3) else 'th'}"


def _window_stats(conn, start: date, end: date) -> dict:
    row = conn.execute("""
        SELECT COUNT(*) AS n,
               COALESCE(SUM(distance_miles), 0)   AS miles,
               COALESCE(SUM(moving_time_min), 0)  AS minutes
        FROM   activities
        WHERE  date >= ? AND date <= ?
    """, (start.isoformat(), end.isoformat())).fetchone()
    return {"n": row["n"], "miles": float(row["miles"]), "hours": float(row["minutes"]) / 60}


def _metric_week_avg(conn, metric: str, start: date, end: date):
    row = conn.execute("""
        SELECT AVG(value) FROM health_metrics
        WHERE  metric = ? AND date >= ? AND date <= ?
    """, (metric, start.isoformat(), end.isoformat())).fetchone()
    return float(row[0]) if row[0] is not None else None


def get_weekly_digest(*, conn) -> dict:
    """Last 7 days (incl. today) vs the 7 before, as narrative sections."""
    from backend.services.correlation_service import (
        get_effect_findings, get_efficiency_trend,
    )

    today = date.today()
    week_start = today - timedelta(days=6)
    prev_start, prev_end = week_start - timedelta(days=7), week_start - timedelta(days=1)

    this = _window_stats(conn, week_start, today)
    prev = _window_stats(conn, prev_start, prev_end)

    sections = []

    # ── Volume ────────────────────────────────────────────────────────────
    if this["n"] == 0:
        sections.append({"kind": "volume", "title": "Volume",
                         "text": "A quiet week — no activities logged in the last 7 days."})
    else:
        text = (f"{this['n']} "
                f"{'activity' if this['n'] == 1 else 'activities'} — "
                f"{this['miles']:.1f} miles in {_fmt_hours(this['hours'])}")
        if prev["miles"] > 0:
            pct = (this["miles"] - prev["miles"]) / prev["miles"] * 100
            if abs(pct) >= 5:
                text += f", {'up' if pct > 0 else 'down'} {abs(pct):.0f}% on the week before"
        sections.append({"kind": "volume", "title": "Volume", "text": text + "."})

    # ── Efficiency trend (reuses the COR-2 verdict verbatim) ──────────────
    eff = get_efficiency_trend(days=120, conn=conn)
    if eff["verdict"]:
        sections.append({"kind": "efficiency", "title": "Efficiency", "text": eff["verdict"]})

    # ── Best moment: this week's most efficient run, ranked vs the year ──
    week_points = [p for p in eff["points"] if p["date"] >= week_start.isoformat()]
    if week_points:
        year = get_efficiency_trend(days=365, conn=conn)["points"]
        best = max(week_points, key=lambda p: p["ef"])
        rank = 1 + sum(1 for p in year if p["ef"] > best["ef"])
        day_name = date.fromisoformat(best["date"]).strftime("%A")
        sections.append({
            "kind": "best_moment", "title": "Best moment",
            "text": (f"{day_name}'s run was your {_ordinal(rank)} most efficient "
                     f"of the past year ({best['ef']:.2f} m/min per bpm)."),
        })

    # ── Body drift: this week's averages vs last week's ──────────────────
    body_bits = []
    for metric, label, unit, decimals, up_is_bad in (
        ("resting_heartrate", "Resting HR", "bpm", 0, True),
        ("hrv_sdnn", "HRV", "ms", 0, False),
        ("sleep_asleep", "sleep", "h/night", 1, False),
    ):
        cur = _metric_week_avg(conn, metric, week_start, today)
        old = _metric_week_avg(conn, metric, prev_start, prev_end)
        if cur is None or old is None:
            continue
        delta = cur - old
        if abs(delta) < (0.5 if unit == "bpm" else 2 if unit == "ms" else 0.25):
            continue
        arrow = "up" if delta > 0 else "down"
        body_bits.append(
            f"{label} averaged {cur:.{decimals}f} {unit}, {arrow} "
            f"{abs(delta):.{decimals if decimals else 1}f} vs last week"
            + (" — worth watching" if (delta > 0) == up_is_bad else "")
        )
    if body_bits:
        sections.append({"kind": "body", "title": "Body",
                         "text": "; ".join(body_bits) + "."})

    # ── One correlation insight (COR-1), when the data supports one ───────
    findings = get_effect_findings(days=365, conn=conn)["findings"]
    if findings:
        sections.append({"kind": "insight", "title": "Pattern",
                         "text": findings[0]["headline"]})

    return {
        "week_start": week_start.isoformat(),
        "week_end":   today.isoformat(),
        "stats": {
            "activities": this["n"],
            "miles": round(this["miles"], 1),
            "hours": round(this["hours"], 2),
            "prev_miles": round(prev["miles"], 1),
        },
        "sections": sections,
    }
