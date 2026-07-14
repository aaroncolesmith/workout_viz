"""
COR-1 (effect analyses) + COR-4 (weekly digest).
"""
from datetime import date, timedelta

from backend.services import health_metrics_service as hm
from backend.services.correlation_service import _welch_t, get_effect_findings
from backend.services.digest_service import get_weekly_digest


def _seed_runs(service, n, start_days_ago, pace_fn, hr=150.0):
    """n runs, every 2 days, pace decided per-index by pace_fn(i)."""
    acts = []
    for i in range(n):
        d = date.today() - timedelta(days=start_days_ago - 2 * i)
        pace = pace_fn(i)
        dist_m = 5.0 * 1609.344
        moving = int(pace * 5.0 * 60)
        acts.append({
            "id": 9000 + i, "name": f"Run {i}", "type": "Run", "sport_type": "Run",
            "start_date": f"{d.isoformat()}T14:00:00Z",
            "start_date_local": f"{d.isoformat()}T07:00:00",
            "distance": dist_m, "moving_time": moving, "elapsed_time": moving,
            "average_speed": dist_m / moving, "average_heartrate": hr,
            "max_heartrate": hr + 15, "has_heartrate": True, "trainer": False,
        })
    service.add_activities(acts)
    return acts


def test_welch_t_sanity():
    assert _welch_t([1, 1, 1], [1, 1, 1]) is None            # zero variance
    t = _welch_t([8.0, 8.1, 8.05, 7.95] * 5, [8.5, 8.6, 8.55, 8.45] * 5)
    assert t < -2                                            # clearly separated


def test_sleep_effect_detected(seeded_backend):
    svc = seeded_backend["service"]
    conn = svc._conn()
    # 30 runs over 60 days; even-indexed runs follow 8h sleep and are 15 s/mi
    # faster; odd-indexed follow 6h sleep.
    runs = _seed_runs(svc, 30, 60, lambda i: 8.0 if i % 2 == 0 else 8.25)
    samples = []
    for i, a in enumerate(runs):
        d = a["start_date_local"][:10]
        samples.append({"metric": "sleep_asleep", "date": d,
                        "value": 8.0 if i % 2 == 0 else 6.0})
    hm.upsert_metrics(conn, samples)

    result = get_effect_findings(days=365, conn=conn)
    sleep = next((f for f in result["findings"] if f["factor"] == "sleep"), None)
    assert sleep is not None
    assert "after 7+ hours of sleep" in sleep["headline"]
    assert sleep["delta_sec_mi"] >= 10
    assert sleep["cohorts"][0]["n"] >= 8 and sleep["cohorts"][1]["n"] >= 8
    # No HRV/RHR data seeded → no fabricated findings for them
    assert all(f["factor"] not in ("hrv", "rhr") for f in result["findings"])


def test_no_finding_when_no_signal(seeded_backend):
    svc = seeded_backend["service"]
    conn = svc._conn()
    # Same pace regardless of sleep → nothing must be reported
    runs = _seed_runs(svc, 30, 60, lambda i: 8.1)
    hm.upsert_metrics(conn, [
        {"metric": "sleep_asleep", "date": a["start_date_local"][:10],
         "value": 8.0 if i % 2 == 0 else 6.0}
        for i, a in enumerate(runs)
    ])
    result = get_effect_findings(days=365, conn=conn)
    assert all(f["factor"] != "sleep" for f in result["findings"])


def test_too_few_runs_returns_nothing(seeded_backend):
    conn = seeded_backend["service"]._conn()
    result = get_effect_findings(days=3650, conn=conn)
    assert result["findings"] == []
    assert result["runs_analyzed"] < 16


# ── Weekly digest ────────────────────────────────────────────────────────────

def test_digest_quiet_week(seeded_backend):
    # Seeded activities are months old — the digest must degrade gracefully
    d = get_weekly_digest(conn=seeded_backend["service"]._conn())
    assert d["stats"]["activities"] == 0
    assert any(s["kind"] == "volume" and "quiet week" in s["text"]
               for s in d["sections"])


def test_digest_with_recent_training(seeded_backend):
    svc = seeded_backend["service"]
    # 7 runs in the last 13 days (≈ one every 2 days spanning both windows)
    _seed_runs(svc, 7, 13, lambda i: 8.0)
    d = get_weekly_digest(conn=svc._conn())
    assert d["stats"]["activities"] >= 3
    kinds = [s["kind"] for s in d["sections"]]
    assert "volume" in kinds
    assert "best_moment" in kinds          # runs this week have EF
    vol = next(s for s in d["sections"] if s["kind"] == "volume")
    assert "miles" in vol["text"]
