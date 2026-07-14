"""
Health metrics service tests (BIO) — upsert, rolling means, comparisons, summary.

Uses seeded_backend so the encrypted per-device DB (and its migration path
that creates health_metrics) is exercised end-to-end.
"""
from datetime import date, timedelta

from backend.services import health_metrics_service as hm


def _days_ago(n: int) -> str:
    return (date(2026, 7, 10) - timedelta(days=n)).isoformat()


def _seed_rhr(conn, values_by_days_ago: dict):
    samples = [
        {"metric": "resting_heartrate", "date": _days_ago(n), "value": v}
        for n, v in values_by_days_ago.items()
    ]
    return hm.upsert_metrics(conn, samples)


# ── upsert ────────────────────────────────────────────────────────────────────

def test_upsert_adds_updates_and_skips(seeded_backend):
    conn = seeded_backend["service"]._conn()

    result = hm.upsert_metrics(conn, [
        {"metric": "resting_heartrate", "date": "2026-07-09", "value": 52.0},
        {"metric": "resting_heartrate", "date": "2026-07-10", "value": 51.0},
        {"metric": "hrv_sdnn",          "date": "2026-07-10", "value": 68.0},
        {"metric": "not_a_metric",      "date": "2026-07-10", "value": 1.0},
        {"metric": "resting_heartrate", "date": "July 10",    "value": 50.0},
        {"metric": "resting_heartrate", "date": "2026-07-08", "value": -4.0},
        {"metric": "resting_heartrate", "date": "2026-07-07", "value": float("nan")},
    ])
    assert result["added"] == 3
    assert result["updated"] == 0
    assert result["skipped"] == 4
    assert result["unknown_metrics"] == ["not_a_metric"]

    # Re-upsert same (metric, day) → updated, value replaced, no duplicate row
    result = hm.upsert_metrics(conn, [
        {"metric": "resting_heartrate", "date": "2026-07-10", "value": 53.0},
    ])
    assert result == {"added": 0, "updated": 1, "skipped": 0, "unknown_metrics": []}

    rows = conn.execute(
        "SELECT value FROM health_metrics WHERE metric='resting_heartrate' AND date='2026-07-10'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["value"] == 53.0


# ── series + rolling means ───────────────────────────────────────────────────

def test_series_rolling_means(seeded_backend):
    conn = seeded_backend["service"]._conn()
    # 10 consecutive days, values 50..59 (oldest→newest)
    _seed_rhr(conn, {n: 59 - n for n in range(10)})

    series = hm.get_metric_series(conn, "resting_heartrate", days=7)
    assert series["unit"] == "bpm"
    assert len(series["points"]) == 7  # anchored at latest day with data

    latest = series["points"][-1]
    assert latest["value"] == 59
    # 7d rolling = mean(53..59) = 56
    assert latest["rolling_7d"] == 56.0
    # 30d rolling window only has 10 values: mean(50..59) = 54.5
    assert latest["rolling_30d"] == 54.5


def test_series_handles_gaps(seeded_backend):
    conn = seeded_backend["service"]._conn()
    # Data on day-0, day-2, day-3 only (day-1 missing)
    _seed_rhr(conn, {0: 60, 2: 50, 3: 40})

    series = hm.get_metric_series(conn, "resting_heartrate", days=90)
    assert [p["value"] for p in series["points"]] == [40, 50, 60]
    # Rolling 7d at the latest day averages the 3 values present in-window
    assert series["points"][-1]["rolling_7d"] == 50.0


# ── comparison block ─────────────────────────────────────────────────────────

def test_comparison_deltas(seeded_backend):
    conn = seeded_backend["service"]._conn()
    # Baseline: 55 bpm for the 30 days before the anchor; anchor day = 50
    values = {n: 55 for n in range(1, 31)}
    values[0] = 50
    _seed_rhr(conn, values)

    c = hm.get_metric_comparison(conn, "resting_heartrate")
    assert c["today"] == 50
    assert c["vs_yesterday"] == -5.0
    assert c["vs_7d_avg"] == -5.0     # trailing windows exclude the anchor day
    assert c["vs_30d_avg"] == -5.0
    assert c["avg_365d"] == 55.0
    # Flat baseline → zero-width band; 50 falls below it
    assert c["baseline_band"] == {"mean": 55.0, "lower": 55.0, "upper": 55.0}
    assert c["out_of_band"] is True
    assert c["date"] == _days_ago(0)
    assert len(c["spark_30d"]) > 0


def test_comparison_none_without_data(seeded_backend):
    conn = seeded_backend["service"]._conn()
    assert hm.get_metric_comparison(conn, "vo2max") is None


def test_comparison_baseline_needs_enough_points(seeded_backend):
    conn = seeded_backend["service"]._conn()
    _seed_rhr(conn, {0: 50, 1: 55, 2: 54})  # only 2 baseline points before anchor
    c = hm.get_metric_comparison(conn, "resting_heartrate")
    assert c["baseline_band"] is None
    assert c["out_of_band"] is False
    assert c["vs_yesterday"] == -5.0


# ── summary ──────────────────────────────────────────────────────────────────

def test_summary_lists_only_metrics_with_data(seeded_backend):
    conn = seeded_backend["service"]._conn()
    hm.upsert_metrics(conn, [
        {"metric": "hrv_sdnn",          "date": "2026-07-10", "value": 70.0},
        {"metric": "resting_heartrate", "date": "2026-07-10", "value": 52.0},
        {"metric": "sleep_asleep",      "date": "2026-07-10", "value": 7.4},
    ])
    summary = hm.get_health_summary(conn)
    slugs = [m["metric"] for m in summary["metrics"]]
    # KNOWN_METRICS declaration order, only metrics with data
    assert slugs == ["resting_heartrate", "hrv_sdnn", "sleep_asleep"]
    assert all(m["today"] is not None for m in summary["metrics"])
