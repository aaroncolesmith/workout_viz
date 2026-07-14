"""
COR-2 — Efficiency Factor trend + aerobic decoupling.
RDY-4 — readiness history.
"""
from datetime import date, timedelta

from backend.services import health_metrics_service as hm
from backend.services.correlation_service import _decoupling, _ef, get_efficiency_trend
from backend.services.fitness_service import get_readiness_history


# ── EF math ──────────────────────────────────────────────────────────────────

def test_ef_definition():
    # 8:00/mi at 160 bpm → (1609.344/8) m/min / 160 bpm
    assert abs(_ef(8.0, 160.0) - (1609.344 / 8 / 160)) < 1e-9
    assert _ef(0, 160) is None
    assert _ef(8.0, None) is None


def _splits(grain, total_miles, pace_by_half, hr_by_half):
    """Uniform splits with different pace/HR per half."""
    n = int(round(total_miles / grain))
    out = []
    for b in range(1, n + 1):
        mile = round(b * grain, 3)
        half = 0 if mile <= total_miles / 2 else 1
        out.append({
            "split_number": b,
            "time_seconds": pace_by_half[half] * 60 * grain,
            "total_distance_miles": mile,
            "avg_heartrate": hr_by_half[half],
        })
    return out


def test_decoupling_zero_when_steady():
    splits = _splits(0.05, 6.0, (9.0, 9.0), (145.0, 145.0))
    assert _decoupling(splits) == 0.0


def test_decoupling_positive_when_fading():
    # Same pace both halves but HR drifts 145 → 160: EF decays ~9.4%
    splits = _splits(0.05, 6.0, (9.0, 9.0), (145.0, 160.0))
    d = _decoupling(splits)
    assert d is not None and 8.5 < d < 10.5


def test_decoupling_grain_agnostic():
    a = _decoupling(_splits(0.1, 6.0, (9.0, 9.5), (145.0, 152.0)))
    b = _decoupling(_splits(0.05, 6.0, (9.0, 9.5), (145.0, 152.0)))
    assert abs(a - b) < 0.3


# ── Efficiency trend over seeded activities ──────────────────────────────────

def test_efficiency_trend_from_db(seeded_backend):
    conn = seeded_backend["service"]._conn()
    result = get_efficiency_trend(days=3650, conn=conn)
    # Seeded runs: 101/102 are 5 mi (qualify), 103 is 10 mi; all have HR
    assert len(result["points"]) == 3
    p = result["points"][0]
    assert p["ef"] > 0 and p["ef_rolling"] > 0
    # Too few points for a verdict window — must not fabricate one
    assert result["verdict"] is None
    # The ride is excluded from a Run trend
    assert all(pt["activity_id"] != 104 for pt in result["points"])


# ── Readiness history (RDY-4) ────────────────────────────────────────────────

def test_readiness_history_shape_and_body_blend(seeded_backend):
    conn = seeded_backend["service"]._conn()
    # Body metrics for the last 40 days: stable baselines, HRV crash yesterday
    samples = []
    for n in range(40):
        d = (date.today() - timedelta(days=n)).isoformat()
        samples.append({"metric": "hrv_sdnn", "date": d,
                        "value": 40.0 if n == 1 else 70.0})
    hm.upsert_metrics(conn, samples)

    history = get_readiness_history(days=30, conn=conn)
    assert len(history) == 30
    assert history[-1]["date"] == date.today().strftime("%Y-%m-%d")

    by_date = {h["date"]: h for h in history}
    yesterday = by_date[(date.today() - timedelta(days=1)).isoformat()]
    day_before = by_date[(date.today() - timedelta(days=2)).isoformat()]
    # HRV crash day scores below its neighbours (same load, worse body signal)
    assert yesterday["score"] < day_before["score"]
    assert yesterday["score"] < yesterday["load_score"]
    # Seeded activities are months old → no training stress in this window
    assert all(h["hard_on_red"] is False for h in history)
