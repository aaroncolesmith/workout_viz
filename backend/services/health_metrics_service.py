"""
Health Metrics Service (BIO) — daily biometrics storage + rolling-average trends.

Stores one row per (metric, day) in the per-user health_metrics table and
answers "how does this compare to yesterday / last week / last month / last
year?".  All baseline comparisons use trailing rolling means (excluding the
latest day) rather than single-day values, so one anomalous night doesn't
read as a trend.

Comparison semantics, anchored at the most recent day with data:
    today          latest daily value
    vs_yesterday   today − previous calendar day's value (raw, may be None)
    vs_7d_avg      today − mean of the 7 days before it
    vs_30d_avg     today − mean of the 30 days before it
    vs_365d_avg    today − mean of the 365 days before it
    baseline_band  mean ± 1σ of the trailing 60 days (before today)

Windows are calendar-day windows over whatever values exist inside them —
missing days simply don't contribute.

No global connections: every function takes an explicit sqlite conn
(same convention as the other conn=-injected services).
"""
import math
import logging
from datetime import date as _date, datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Canonical metric slugs ↔ storage units.  The iOS SyncEngine and the XML
# importer must both map HK identifiers onto these slugs; unknown slugs are
# rejected at ingest so a client typo can't silently fork a metric series.
KNOWN_METRICS: Dict[str, dict] = {
    "resting_heartrate": {"unit": "bpm",       "label": "Resting Heart Rate"},
    "hrv_sdnn":          {"unit": "ms",        "label": "Heart Rate Variability"},
    "vo2max":            {"unit": "mL/kg/min", "label": "VO₂ Max"},
    "respiratory_rate":  {"unit": "br/min",    "label": "Respiratory Rate"},
    "blood_oxygen":      {"unit": "%",         "label": "Blood Oxygen"},
    "steps":             {"unit": "steps",     "label": "Steps"},
    "active_energy":     {"unit": "kcal",      "label": "Active Energy"},
    "body_mass":         {"unit": "kg",        "label": "Body Mass"},
    "sleep_asleep":      {"unit": "hr",        "label": "Sleep"},
    "sleep_in_bed":      {"unit": "hr",        "label": "Time in Bed"},
}

# Display order for the summary endpoint (dashboard tiles)
_SUMMARY_ORDER = list(KNOWN_METRICS.keys())

_BASELINE_DAYS = 60
_SPARK_DAYS = 30


# ── ingest ────────────────────────────────────────────────────────────────────

def upsert_metrics(conn, samples: List[dict]) -> dict:
    """
    Batch-upsert daily metric samples: {metric, date, value, min?, max?, source_id?}.

    Returns {"added", "updated", "skipped", "unknown_metrics"}.  Rows with an
    unknown metric slug, a malformed date, or a non-finite/negative value are
    skipped (counted), never partially written.
    """
    added = updated = skipped = 0
    unknown: set = set()

    for s in samples:
        metric = s.get("metric")
        if metric not in KNOWN_METRICS:
            if metric:
                unknown.add(metric)
            skipped += 1
            continue

        date_str = s.get("date")
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except (TypeError, ValueError):
            skipped += 1
            continue

        value = s.get("value")
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            skipped += 1
            continue

        exists = conn.execute(
            "SELECT 1 FROM health_metrics WHERE metric = ? AND date = ?",
            (metric, date_str),
        ).fetchone()

        conn.execute(
            """
            INSERT INTO health_metrics (metric, date, value, min_value, max_value, source_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (metric, date) DO UPDATE SET
                value      = excluded.value,
                min_value  = excluded.min_value,
                max_value  = excluded.max_value,
                source_id  = excluded.source_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (metric, date_str, float(value), s.get("min"), s.get("max"), s.get("source_id")),
        )
        if exists:
            updated += 1
        else:
            added += 1

    conn.commit()
    if unknown:
        logger.warning(f"Ignored unknown health metric slugs: {sorted(unknown)}")
    return {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "unknown_metrics": sorted(unknown),
    }


# ── reads ─────────────────────────────────────────────────────────────────────

def _load_series(conn, metric: str) -> Dict[_date, float]:
    rows = conn.execute(
        "SELECT date, value FROM health_metrics WHERE metric = ? ORDER BY date",
        (metric,),
    ).fetchall()
    out: Dict[_date, float] = {}
    for r in rows:
        try:
            out[_date.fromisoformat(r["date"])] = r["value"]
        except ValueError:
            continue
    return out


def _window_mean(by_date: Dict[_date, float], end: _date, days: int) -> Optional[float]:
    """Mean of values in the calendar window [end - days + 1, end]; None if empty."""
    vals = [by_date[end - timedelta(days=i)]
            for i in range(days)
            if (end - timedelta(days=i)) in by_date]
    return sum(vals) / len(vals) if vals else None


def _round(v: Optional[float]) -> Optional[float]:
    return round(v, 2) if v is not None else None


def get_metric_comparison(conn, metric: str, by_date: Optional[Dict[_date, float]] = None) -> Optional[dict]:
    """
    Rolling-average comparison block for one metric, anchored at the most
    recent day with data.  Returns None when the metric has no rows.
    """
    if by_date is None:
        by_date = _load_series(conn, metric)
    if not by_date:
        return None

    latest = max(by_date)
    today_val = by_date[latest]
    yesterday_val = by_date.get(latest - timedelta(days=1))

    # Trailing windows END the day before the anchor, so the anchor day's
    # own value never dilutes the baseline it's compared against.
    prior = latest - timedelta(days=1)
    avg_7d = _window_mean(by_date, prior, 7)
    avg_30d = _window_mean(by_date, prior, 30)
    avg_365d = _window_mean(by_date, prior, 365)

    band = None
    out_of_band = False
    baseline_vals = [by_date[prior - timedelta(days=i)]
                     for i in range(_BASELINE_DAYS)
                     if (prior - timedelta(days=i)) in by_date]
    if len(baseline_vals) >= 5:  # a band from fewer points is noise, not a baseline
        mean = sum(baseline_vals) / len(baseline_vals)
        std = math.sqrt(sum((v - mean) ** 2 for v in baseline_vals) / len(baseline_vals))
        band = {"mean": _round(mean), "lower": _round(mean - std), "upper": _round(mean + std)}
        out_of_band = today_val < band["lower"] or today_val > band["upper"]

    # 30-day sparkline of the 7-day rolling mean (dashboard tiles)
    spark: List[float] = []
    for i in range(_SPARK_DAYS - 1, -1, -1):
        m = _window_mean(by_date, latest - timedelta(days=i), 7)
        if m is not None:
            spark.append(round(m, 2))

    meta = KNOWN_METRICS[metric]
    return {
        "metric": metric,
        "label": meta["label"],
        "unit": meta["unit"],
        "date": latest.isoformat(),
        "today": _round(today_val),
        "vs_yesterday": _round(today_val - yesterday_val) if yesterday_val is not None else None,
        "vs_7d_avg": _round(today_val - avg_7d) if avg_7d is not None else None,
        "vs_30d_avg": _round(today_val - avg_30d) if avg_30d is not None else None,
        "vs_365d_avg": _round(today_val - avg_365d) if avg_365d is not None else None,
        "avg_7d": _round(avg_7d),
        "avg_30d": _round(avg_30d),
        "avg_365d": _round(avg_365d),
        "baseline_band": band,
        "out_of_band": out_of_band,
        "spark_30d": spark,
    }


def get_metric_series(conn, metric: str, days: int = 90) -> dict:
    """
    Daily series (last `days` days, anchored at the most recent day with data)
    with 7d/30d rolling means per point, plus the comparison block.
    """
    meta = KNOWN_METRICS[metric]
    by_date = _load_series(conn, metric)

    points = []
    if by_date:
        latest = max(by_date)
        start = latest - timedelta(days=days - 1)
        for d in sorted(dd for dd in by_date if dd >= start):
            points.append({
                "date": d.isoformat(),
                "value": _round(by_date[d]),
                "rolling_7d": _round(_window_mean(by_date, d, 7)),
                "rolling_30d": _round(_window_mean(by_date, d, 30)),
            })

    return {
        "metric": metric,
        "label": meta["label"],
        "unit": meta["unit"],
        "days": days,
        "points": points,
        "comparison": get_metric_comparison(conn, metric, by_date=by_date),
    }


def get_health_summary(conn) -> dict:
    """Today's snapshot of every metric that has data — one call for the dashboard."""
    present = {
        r["metric"] for r in
        conn.execute("SELECT DISTINCT metric FROM health_metrics").fetchall()
    }
    metrics = []
    for slug in _SUMMARY_ORDER:
        if slug not in present:
            continue
        cmp_block = get_metric_comparison(conn, slug)
        if cmp_block:
            metrics.append(cmp_block)
    return {"metrics": metrics}
