"""
CMP-1 / CMP-2 — auto post-workout comparison + relative effort.

seeded_backend provides 3 runs (101 Tempo 5mi/40min, 102 Progression
5.1mi/41min, 103 Long 10mi/90min) and 1 ride (104).
"""
from backend.services.comparison_service import get_comparison
from backend.services.fitness_service import get_relative_effort


def _link_route(conn, route_name, activity_ids):
    cur = conn.execute(
        "INSERT INTO routes (name, activity_type, activity_count) VALUES (?, 'Run', ?)",
        (route_name, len(activity_ids)),
    )
    route_id = cur.lastrowid
    for aid in activity_ids:
        conn.execute(
            "INSERT INTO route_activities (route_id, activity_id, similarity_score) VALUES (?, ?, 0.95)",
            (route_id, aid),
        )
    conn.commit()
    return route_id


# ── relative effort (CMP-2) ──────────────────────────────────────────────────

def test_relative_effort_ranks_long_run_hardest(seeded_backend):
    conn = seeded_backend["service"]._conn()
    # Window ends at the activity's own date: 103 (Mar 5) sees 101/102/103,
    # not the Mar 7 ride — percentiles reflect what was true at the time.
    effort = get_relative_effort(103, conn=conn)  # 90-min long run w/ HR
    assert effort is not None
    assert effort["rank"] == 1
    assert effort["of"] == 3
    assert effort["percentile"] == 100.0
    assert "1st hardest of 3" in effort["label"]
    assert effort["trimp"] > 0

    # The Mar 7 easy ride sees all 4; the long run and progression run beat it
    easy = get_relative_effort(104, conn=conn)
    assert easy["rank"] == 3
    assert easy["of"] == 4
    assert easy["percentile"] == 50.0


# ── cohort cascade (CMP-1) ───────────────────────────────────────────────────

def test_route_cohort_wins_and_ranks_on_time(seeded_backend):
    svc = seeded_backend["service"]
    route_id = _link_route(svc._conn(), "Riverside Loop", [101, 102])
    svc._invalidate_all_caches()

    c = get_comparison(101, data_service=svc)
    assert c["cohort"]["kind"] == "route"
    assert c["cohort"]["route_id"] == route_id
    assert "Riverside Loop" in c["cohort"]["label"]
    assert c["rank_metric"] == "time"
    # 101 (40 min) beats 102 (41 min)
    assert (c["rank"], c["rank_of"]) == (1, 2)
    assert "1st fastest of 2 on Riverside Loop" in c["verdict"]
    # 101: pace 8.00 vs cohort avg 8.05 (within 3s/mi noise), HR 155 vs 157
    assert c["efficiency"] == "consistent"
    assert c["deltas"]["time_vs_avg_sec"] == -60.0
    # History: both attempts, current flagged, sorted by date
    assert [h["is_current"] for h in c["history"]] == [True, False]
    assert c["effort"] is not None


def test_similarity_fallback_without_routes(seeded_backend):
    svc = seeded_backend["service"]
    # 102 vs 101: nearly identical features + same polyline → similar cohort
    c = get_comparison(102, data_service=svc)
    assert c["cohort"] is not None
    assert c["cohort"]["kind"] in ("similar", "distance")
    assert c["rank_metric"] == "pace"
    # 102 pace 8.05 is slower than 101's 8.00 → rank 2
    assert (c["rank"], c["rank_of"]) == (2, 2)
    assert c["verdict"]


def test_no_cohort_still_returns_effort_verdict(seeded_backend):
    svc = seeded_backend["service"]
    # 104 is the only ride: no route, no similar, no distance-band matches
    c = get_comparison(104, data_service=svc)
    assert c["cohort"] is None
    assert c["rank"] is None
    assert c["deltas"] is None
    assert c["effort"] is not None
    assert "hardest of 4" in c["verdict"]


def test_missing_activity_returns_none(seeded_backend):
    assert get_comparison(999999, data_service=seeded_backend["service"]) is None
