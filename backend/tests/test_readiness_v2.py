"""
Readiness 2.0 (RDY-1 / RDY-2) — real resting HR + body-signal blending.
"""
from datetime import date, timedelta

from backend.services import health_metrics_service as hm
from backend.services.fitness_service import _get_hr_params, get_readiness_v2


def _seed_metric(conn, metric, values_by_days_ago):
    hm.upsert_metrics(conn, [
        {"metric": metric, "date": (date.today() - timedelta(days=n)).isoformat(), "value": v}
        for n, v in values_by_days_ago.items()
    ])


# ── RDY-1: resting HR from measured data ─────────────────────────────────────

def test_resting_hr_derived_from_health_metrics(seeded_backend):
    conn = seeded_backend["service"]._conn()
    assert _get_hr_params(conn)[0] == 60.0          # nothing measured → default

    _seed_metric(conn, "resting_heartrate", {n: 52.0 for n in range(20)})
    assert abs(_get_hr_params(conn)[0] - 52.0) < 0.01

    # Manual setting always wins
    conn.execute("INSERT INTO user_settings (key, value) VALUES ('resting_hr', '48')")
    conn.commit()
    assert _get_hr_params(conn)[0] == 48.0


# ── RDY-2: blended readiness ─────────────────────────────────────────────────

def test_readiness_v2_load_only_without_body_metrics(seeded_backend):
    conn = seeded_backend["service"]._conn()
    r = get_readiness_v2(conn=conn)
    assert [f["name"] for f in r["factors"]] == ["Training load"]
    assert r["score"] == r["factors"][0]["score"]   # weights renormalise to load
    assert "TSB" in r["why"]


def test_readiness_v2_poor_body_signals_drag_score_down(seeded_backend):
    conn = seeded_backend["service"]._conn()
    # Baselines: HRV 70 ms, RHR 52, sleep 7.5h — today: HRV crashed, RHR
    # spiked, short sleep.
    _seed_metric(conn, "hrv_sdnn", {**{n: 70.0 for n in range(1, 31)}, 0: 49.0})
    _seed_metric(conn, "resting_heartrate", {**{n: 52.0 for n in range(1, 31)}, 0: 58.0})
    _seed_metric(conn, "sleep_asleep", {**{n: 7.5 for n in range(1, 31)}, 0: 5.0})

    r = get_readiness_v2(conn=conn)
    names = [f["name"] for f in r["factors"]]
    assert names == ["Training load", "HRV", "Resting HR", "Sleep"]

    load_score = r["factors"][0]["score"]
    assert r["score"] < load_score                   # body signals pull it down
    hrv = next(f for f in r["factors"] if f["name"] == "HRV")
    assert hrv["score"] < 20                         # −30% HRV ≈ bottom of scale
    assert "backing off" in r["recommendation"]
    assert "HRV 49 ms" in r["why"]


def test_readiness_v2_ignores_stale_body_metrics(seeded_backend):
    conn = seeded_backend["service"]._conn()
    # Metrics exist but the newest is 10 days old — can't describe today.
    _seed_metric(conn, "hrv_sdnn", {n: 70.0 for n in range(10, 40)})
    r = get_readiness_v2(conn=conn)
    assert [f["name"] for f in r["factors"]] == ["Training load"]
