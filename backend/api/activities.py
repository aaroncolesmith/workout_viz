"""
Activity API routes — CRUD + filtering, all scoped to the authenticated user (DATA-5).
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional

from backend.api.deps import get_current_user
from backend.services.data_service import get_data_service
from backend.services.similarity_service import find_similar_activities
from backend.services.pca_service import get_activity_pca
from backend.services.fitness_service import get_fitness_data, _get_hr_params, get_readiness
from backend.services.insight_service import get_insights
from backend.services.race_predictor_service import get_race_predictions
from backend.services.route_service import (
    build_route_clusters, get_routes, get_route_activities,
    rename_route, get_build_status,
)
from backend.models import schemas

router = APIRouter(prefix="/api", tags=["activities"])


# ── Strava sync (dormant — Strava shelved) ────────────────────────────────────

@router.post("/activities/sync", response_model=schemas.SyncStartResponse)
def sync_activities(
    deep: bool = Query(False),
    user_id: str = Depends(get_current_user),
):
    """Strava sync — dormant; kept so the frontend doesn't 404."""
    return {"status": "error", "message": "Strava sync is not available."}


@router.get("/activities/sync/status", response_model=schemas.SyncStatusResponse)
def get_sync_status(user_id: str = Depends(get_current_user)):
    return {"status": "idle", "message": "Strava sync is not available."}


@router.post("/activities/splits/sync")
def start_splits_backfill(
    limit: Optional[int] = Query(None),
    types: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user),
):
    return {"status": "error", "message": "Strava sync is not available."}


@router.get("/activities/splits/sync/status")
def get_splits_sync_status(user_id: str = Depends(get_current_user)):
    return {"status": "idle"}


# ── Activity list / detail ────────────────────────────────────────────────────

@router.get("/activities", response_model=schemas.ActivityListResponse)
def list_activities(
    type: Optional[str] = Query(None),
    sport_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    min_distance: Optional[float] = Query(None),
    max_distance: Optional[float] = Query(None),
    limit: int = Query(50, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user),
):
    data = get_data_service(user_id)
    activities, total = data.get_activities(
        activity_type=type, sport_type=sport_type,
        date_from=date_from, date_to=date_to,
        min_distance=min_distance, max_distance=max_distance,
        limit=limit, offset=offset,
    )
    return {"activities": activities, "total": total, "limit": limit, "offset": offset}


@router.get("/activities/types", response_model=schemas.ActivityTypesResponse)
def list_activity_types(user_id: str = Depends(get_current_user)):
    data = get_data_service(user_id)
    return {"types": data.get_activity_types()}


@router.get("/activities/{activity_id}/insights", response_model=schemas.InsightResponse)
def get_activity_insights(
    activity_id: int,
    user_id: str = Depends(get_current_user),
):
    svc = get_data_service(user_id)
    insights = get_insights(activity_id, conn=svc._conn())

    # CMP-3: the comparison verdict backs up the insight headline — a workout
    # with no PR or segment story still gets "your 3rd fastest on this route".
    from backend.services.comparison_service import get_comparison
    comp = get_comparison(activity_id, data_service=svc)
    if comp and comp.get("verdict"):
        insights["comparison"] = {
            "verdict":    comp["verdict"],
            "efficiency": comp.get("efficiency"),
            "rank":       comp.get("rank"),
            "rank_of":    comp.get("rank_of"),
        }
        if not insights.get("headline"):
            insights["headline"] = comp["verdict"]
    return insights


@router.get("/activities/prs", response_model=schemas.PRsResponse)
def get_recent_prs(
    since: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user),
):
    data = get_data_service(user_id)
    prs = data.get_recent_prs(limit=limit, since=since)
    return {"prs": prs, "count": len(prs)}


@router.get("/activities/prs/best")
def get_best_prs(user_id: str = Depends(get_current_user)):
    conn = get_data_service(user_id)._conn()
    rows = conn.execute("""
        WITH ranked AS (
            SELECT p.*, a.type AS activity_type,
                   ROW_NUMBER() OVER (
                       PARTITION BY a.type, p.distance_label
                       ORDER BY p.time_seconds ASC
                   ) AS rn
              FROM pr_events p
              LEFT JOIN activities a ON a.id = p.activity_id
             WHERE a.type IS NOT NULL
        )
        SELECT activity_id, activity_name, activity_type, date,
               distance_label, distance_miles, time_seconds, time_str, pace_str
          FROM ranked
         WHERE rn = 1
    """).fetchall()
    return {"prs": [dict(r) for r in rows], "count": len(rows)}


@router.get("/activities/{activity_id}", response_model=schemas.ActivityDetail)
def get_activity(activity_id: int, user_id: str = Depends(get_current_user)):
    data = get_data_service(user_id)
    activity = data.get_activity(activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.get("/activities/{activity_id}/splits", response_model=schemas.SplitsResponse)
def get_activity_splits(activity_id: int, user_id: str = Depends(get_current_user)):
    data = get_data_service(user_id)
    splits = data.get_splits(activity_id)
    return {"splits": splits, "count": len(splits)}


# ── Swim laps ─────────────────────────────────────────────────────────────────

def _compute_swim_best_sets(laps: list, pool_length_meters: float) -> dict:
    if not pool_length_meters or pool_length_meters <= 0:
        return {}
    active_laps = [l for l in laps if not l["is_rest"]]
    if not active_laps:
        return {}

    remainder = pool_length_meters % 22.86
    is_yards = remainder < 1.0
    if is_yards:
        pool_unit = round(pool_length_meters / 0.9144)
        unit = 'yd'
        targets = [
            ('fastest_lap',  f'{pool_unit}yd', 1),
            ('fastest_50',   '50yd',           max(1, round(50  / pool_unit))),
            ('fastest_500',  '500yd',          max(1, round(500  / pool_unit))),
            ('fastest_1000', '1000yd',         max(1, round(1000 / pool_unit))),
        ]
    else:
        pool_unit = round(pool_length_meters)
        unit = 'm'
        targets = [
            ('fastest_lap',  f'{pool_unit}m', 1),
            ('fastest_50',   '50m',           max(1, round(50  / pool_unit))),
            ('fastest_500',  '500m',          max(1, round(500  / pool_unit))),
            ('fastest_1000', '1000m',         max(1, round(1000 / pool_unit))),
        ]

    results = {}
    for key, label, n_active in targets:
        if n_active > len(active_laps):
            continue
        best = None
        for i in range(len(active_laps) - n_active + 1):
            start_num = active_laps[i]["lap_number"]
            end_num   = active_laps[i + n_active - 1]["lap_number"]
            wall_time = sum(
                l["duration_seconds"] for l in laps
                if start_num <= l["lap_number"] <= end_num
            )
            if best is None or wall_time < best["time_seconds"]:
                best = {"time_seconds": round(wall_time, 1), "start_lap": start_num,
                        "end_lap": end_num, "n_laps": n_active, "label": label}
        if best:
            results[key] = best
    return results


@router.get("/activities/{activity_id}/swim-laps")
def get_swim_laps(activity_id: int, user_id: str = Depends(get_current_user)):
    conn = get_data_service(user_id)._conn()
    activity = conn.execute(
        "SELECT pool_length_meters, distance_miles, moving_time_min FROM activities WHERE id = ?",
        (activity_id,)
    ).fetchone()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    rows = conn.execute(
        """SELECT lap_number, distance_meters, duration_seconds,
                  stroke_type, stroke_count, avg_heartrate, is_rest
             FROM swim_laps WHERE activity_id = ? ORDER BY lap_number""",
        (activity_id,)
    ).fetchall()

    pool_m = activity["pool_length_meters"]
    laps = []
    for r in rows:
        dur = r["duration_seconds"]
        dist = r["distance_meters"] or pool_m
        pace_per_100 = (dur / dist * 100) if dist and dist > 0 else None
        laps.append({
            "lap_number": r["lap_number"], "distance_meters": dist,
            "duration_seconds": dur, "stroke_type": r["stroke_type"],
            "stroke_count": r["stroke_count"], "avg_heartrate": r["avg_heartrate"],
            "is_rest": bool(r["is_rest"]),
            "pace_per_100": round(pace_per_100, 1) if pace_per_100 else None,
        })

    active_laps = [l for l in laps if not l["is_rest"]]
    avg_pace = (
        sum(l["pace_per_100"] for l in active_laps if l["pace_per_100"]) / len(active_laps)
        if active_laps else None
    )
    best_pace = min((l["pace_per_100"] for l in active_laps if l["pace_per_100"]), default=None)
    best_sets = _compute_swim_best_sets(laps, pool_m)

    return {
        "laps": laps, "pool_length_meters": pool_m,
        "avg_pace_per_100": round(avg_pace, 1) if avg_pace else None,
        "best_pace_per_100": round(best_pace, 1) if best_pace else None,
        "lap_count": len(laps), "active_lap_count": len(active_laps),
        "best_sets": best_sets,
    }


# ── Segments / summaries ──────────────────────────────────────────────────────

@router.post("/activities/{activity_id}/sync_details", response_model=schemas.SyncStartResponse)
def sync_activity_details(activity_id: int, user_id: str = Depends(get_current_user)):
    return {"status": "error", "message": "Strava sync is not available."}


@router.get("/activities/{activity_id}/summary", response_model=schemas.SummarySegmentsResponse)
def get_activity_summary(activity_id: int, user_id: str = Depends(get_current_user)):
    data = get_data_service(user_id)
    summary = data.get_summary(activity_id)
    return {"segments": summary, "count": len(summary)}


@router.get("/activities/{activity_id}/fastest_segments", response_model=schemas.RollingFastestSegmentsResponse)
def get_fastest_segments(activity_id: int, user_id: str = Depends(get_current_user)):
    data = get_data_service(user_id)
    splits = data.get_splits(activity_id)
    if not splits:
        return {"segments": []}

    TARGETS = [
        (1.0,   "1 Mile"), (2.0,   "2 Miles"), (3.107, "5K"),
        (5.0,   "5 Miles"), (6.214, "10K"),
        (13.1,  "Half Marathon"), (26.2, "Marathon"),
    ]

    # Grain-agnostic shared implementation (legacy 0.1-mi + new finer splits).
    from backend.services.splits_service import rolling_fastest_segments

    results = []
    for seg in rolling_fastest_segments(splits, TARGETS):
        t = int(seg["time_seconds"])
        h, m, s = t // 3600, (t % 3600) // 60, t % 60
        time_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        pace_sec = seg["time_seconds"] / seg["distance_miles"]
        pace_str = f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}/mi"
        results.append({
            "label": seg["label"], "distance_miles": seg["distance_miles"],
            "time_seconds": seg["time_seconds"], "time_str": time_str,
            "pace_str": pace_str, "start_mile": seg["start_mile"],
            "end_mile": seg["end_mile"], "avg_hr": seg["avg_heartrate"],
        })
    return {"segments": results}


@router.get("/activities/{activity_id}/comparison", response_model=schemas.ComparisonResponse)
def get_activity_comparison(
    activity_id: int,
    user_id: str = Depends(get_current_user),
):
    """CMP-1 — auto-selected cohort comparison + relative effort verdict."""
    from backend.services.comparison_service import get_comparison

    svc = get_data_service(user_id)
    result = get_comparison(activity_id, data_service=svc)
    if result is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return result


@router.get("/activities/{activity_id}/similar", response_model=schemas.SimilarActivitiesResponse)
def get_similar_activities(
    activity_id: int,
    top_n: int = Query(5, ge=1, le=100),
    user_id: str = Depends(get_current_user),
):
    svc = get_data_service(user_id)
    similar = find_similar_activities(activity_id, top_n=top_n, data_service=svc)
    return {"similar": similar, "count": len(similar)}


@router.get("/similarity/pca", response_model=schemas.PCAResponse)
def get_pca_viz(
    type: str = Query("Run"),
    user_id: str = Depends(get_current_user),
):
    svc = get_data_service(user_id)
    return get_activity_pca(activity_type=type, data_service=svc)


@router.post("/activities/compare", response_model=schemas.CompareResponse)
def compare_activities(
    body: schemas.CompareRequest,
    user_id: str = Depends(get_current_user),
):
    if not body.activity_ids or len(body.activity_ids) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 activity_ids")
    if len(body.activity_ids) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 activities for comparison")
    data = get_data_service(user_id)
    activities = []
    for aid in body.activity_ids:
        activity = data.get_activity(aid)
        if activity:
            activities.append({
                "activity": activity,
                "splits": data.get_splits(aid),
                "summary": data.get_summary(aid),
            })
    return {"comparisons": activities, "count": len(activities)}


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats/overview", response_model=schemas.OverviewStats)
def get_overview(user_id: str = Depends(get_current_user)):
    return get_data_service(user_id).get_overview_stats()


@router.get("/stats/trends", response_model=schemas.TrendsResponse)
def get_trends(
    type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user),
):
    data = get_data_service(user_id)
    trends = data.get_trend_data(activity_type=type, date_from=date_from, date_to=date_to)
    return {"data": trends, "count": len(trends)}


@router.get("/stats/calendar", response_model=schemas.CalendarResponse)
def get_calendar(
    months: int = Query(12, ge=1, le=36),
    user_id: str = Depends(get_current_user),
):
    data = get_data_service(user_id)
    days = data.get_calendar_data(months=months)
    return {"days": days, "months": months}


@router.get("/stats/fitness", response_model=schemas.FitnessResponse)
def get_fitness(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    user_id: str = Depends(get_current_user),
):
    conn = get_data_service(user_id)._conn()
    data = get_fitness_data(date_from=date_from, date_to=date_to, conn=conn)
    resting_hr, max_hr = _get_hr_params(conn)
    return {
        "data": data, "count": len(data),
        "resting_hr": round(resting_hr, 1), "max_hr": round(max_hr, 1),
    }


@router.get("/stats/readiness", response_model=schemas.ReadinessResponse)
def get_readiness_score(user_id: str = Depends(get_current_user)):
    """RDY-2 — training load blended with morning HRV/RHR/sleep deviations."""
    from backend.services.fitness_service import get_readiness_v2

    conn = get_data_service(user_id)._conn()
    return get_readiness_v2(conn=conn)


@router.get("/stats/readiness/history", response_model=schemas.ReadinessHistoryResponse)
def get_readiness_history_route(
    days: int = Query(90, ge=14, le=730),
    user_id: str = Depends(get_current_user),
):
    """RDY-4 — blended readiness per day, with hard-on-red-day flags."""
    from backend.services.fitness_service import get_readiness_history

    svc = get_data_service(user_id)
    cache = svc.get_analytics_cache()
    cache_key = f"readiness:history:{days}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    data = get_readiness_history(days=days, conn=svc._conn())
    result = {"data": data, "count": len(data)}
    cache.set(cache_key, result)
    return result


@router.get("/stats/efficiency", response_model=schemas.EfficiencyTrendResponse)
def get_efficiency_trend_route(
    type: str = Query("Run"),
    days: int = Query(365, ge=30, le=3650),
    user_id: str = Depends(get_current_user),
):
    """COR-2 — Efficiency Factor trend + aerobic decoupling per run."""
    from backend.services.correlation_service import get_efficiency_trend

    svc = get_data_service(user_id)
    cache = svc.get_analytics_cache()
    cache_key = f"efficiency:{type}:{days}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = get_efficiency_trend(days=days, activity_type=type, conn=svc._conn())
    cache.set(cache_key, result)
    return result


@router.get("/stats/correlations", response_model=schemas.EffectFindingsResponse)
def get_correlations_route(
    days: int = Query(365, ge=60, le=3650),
    user_id: str = Depends(get_current_user),
):
    """COR-1 — statistically-gated body→performance findings."""
    from backend.services.correlation_service import get_effect_findings

    svc = get_data_service(user_id)
    cache = svc.get_analytics_cache()
    cache_key = f"correlations:{days}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = get_effect_findings(days=days, conn=svc._conn())
    cache.set(cache_key, result)
    return result


@router.get("/stats/digest", response_model=schemas.WeeklyDigestResponse)
def get_weekly_digest_route(user_id: str = Depends(get_current_user)):
    """COR-4 — the weekly narrative."""
    from backend.services.digest_service import get_weekly_digest

    svc = get_data_service(user_id)
    cache = svc.get_analytics_cache()
    cached = cache.get("digest:weekly")
    if cached is not None:
        return cached
    result = get_weekly_digest(conn=svc._conn())
    cache.set("digest:weekly", result)
    return result


@router.get("/stats/predictions", response_model=schemas.RacePredictionsResponse)
def get_predictions(
    type: str = Query("Run"),
    days: int = Query(90),
    user_id: str = Depends(get_current_user),
):
    conn = get_data_service(user_id)._conn()
    preds = get_race_predictions(activity_type=type, days=days, conn=conn)
    return {"predictions": preds, "activity_type": type, "days": days}


@router.get("/stats/best-segments", response_model=schemas.SegmentTrendResponse)
def get_best_segments_trend(
    type: Optional[str] = Query("Run"),
    distance: float = Query(1.0),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    label: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user),
):
    data = get_data_service(user_id)
    best_efforts = data.get_best_segments(
        activity_type=type, distance_miles=distance,
        date_from=date_from, date_to=date_to,
    )
    label_map = {
        0.25: "1/4 Mile", 0.5: "1/2 Mile", 1.0: "1 Mile", 2.0: "2 Miles",
        3.107: "5K", 5.0: "5 Miles", 6.214: "10K", 10.0: "10 Miles",
        13.1: "Half Marathon", 25.0: "25 Miles", 26.2: "Marathon", 50.0: "50 Miles",
    }
    return {
        "data": best_efforts,
        "distance_miles": distance,
        "label": label_map.get(distance, f"{distance} miles"),
    }


# ── Training Blocks ───────────────────────────────────────────────────────────

import math
from backend.services.fitness_service import get_fitness_data as _get_fitness_data


def _compute_block_metrics(start_date: str, end_date: str, fitness_cache: list, conn) -> dict:
    rows = conn.execute("""
        SELECT type, distance_miles, pace, average_heartrate, total_elevation_gain,
               moving_time_min, date
        FROM activities WHERE date >= ? AND date <= ?
    """, (start_date, end_date)).fetchall()

    activities = [dict(zip(
        ['type','distance_miles','pace','average_heartrate','total_elevation_gain','moving_time_min','date'], r
    )) for r in rows]

    total_miles = sum(a['distance_miles'] or 0 for a in activities)
    run_activities = [a for a in activities if a['type'] == 'Run']
    run_count = len(run_activities)
    total_elevation_ft = sum((a['total_elevation_gain'] or 0) * 3.28084 for a in activities)

    from datetime import date as date_cls
    try:
        d0 = date_cls.fromisoformat(start_date)
        d1 = date_cls.fromisoformat(end_date)
        weeks = max(1.0, (d1 - d0).days / 7.0)
    except Exception:
        weeks = 1.0

    paces = [a['pace'] for a in run_activities if a['pace'] and a['pace'] > 0]
    avg_pace = round(sum(paces) / len(paces), 4) if paces else None
    hrs = [a['average_heartrate'] for a in activities if a['average_heartrate']]
    avg_hr = round(sum(hrs) / len(hrs), 1) if hrs else None

    ctl_start = ctl_end = tsb_start = None
    if fitness_cache:
        pts_before_start = [p for p in fitness_cache if p['date'] <= start_date]
        pts_before_end   = [p for p in fitness_cache if p['date'] <= end_date]
        if pts_before_start:
            p = pts_before_start[-1]
            ctl_start = round(p['ctl'], 1); tsb_start = round(p['tsb'], 1)
        if pts_before_end:
            ctl_end = round(pts_before_end[-1]['ctl'], 1)

    ctl_delta = round(ctl_end - ctl_start, 1) if (ctl_start is not None and ctl_end is not None) else None

    return {
        'activity_count': len(activities), 'run_count': run_count,
        'total_miles': round(total_miles, 1),
        'avg_weekly_miles': round(total_miles / weeks, 1),
        'avg_pace': avg_pace, 'avg_hr': avg_hr,
        'total_elevation_ft': round(total_elevation_ft, 0),
        'ctl_start': ctl_start, 'ctl_end': ctl_end,
        'ctl_delta': ctl_delta, 'tsb_start': tsb_start,
    }


def _compute_delta(current: dict, previous: dict) -> dict | None:
    if not previous:
        return None
    delta = {}
    cp, pp = current.get('avg_pace'), previous.get('avg_pace')
    if cp and pp:
        diff_sec = (cp - pp) * 60
        sign = '+' if diff_sec > 0 else ''
        m = int(abs(diff_sec) // 60); s = int(abs(diff_sec) % 60)
        direction = '↑ faster' if diff_sec < 0 else '↓ slower'
        delta['pace_delta'] = round(diff_sec, 1)
        delta['pace_delta_str'] = f"{sign}{m}:{s:02d}/mi ({direction})"
    cv, pv = current.get('avg_weekly_miles'), previous.get('avg_weekly_miles')
    if cv and pv and pv > 0:
        delta['volume_delta_pct'] = round(((cv - pv) / pv) * 100, 1)
    ch, ph = current.get('avg_hr'), previous.get('avg_hr')
    if ch and ph:
        delta['hr_delta'] = round(ch - ph, 1)
    return delta if delta else None


@router.get("/blocks", response_model=schemas.TrainingBlocksResponse)
def list_blocks(user_id: str = Depends(get_current_user)):
    conn = get_data_service(user_id)._conn()
    rows = conn.execute(
        "SELECT id, name, block_type, start_date, end_date, notes, created_at "
        "FROM training_blocks ORDER BY start_date DESC"
    ).fetchall()
    if not rows:
        return {"blocks": [], "count": 0}

    all_dates = [r[3] for r in rows] + [r[4] for r in rows]
    try:
        fitness_pts = _get_fitness_data(
            date_from=min(all_dates), date_to=max(all_dates), conn=conn
        )
    except Exception:
        fitness_pts = []

    prev_metrics_by_type: dict = {}
    blocks_asc = list(reversed(rows))
    metrics_by_id = {}
    for row in blocks_asc:
        bid, name, btype, sd, ed, notes, created = row
        m = _compute_block_metrics(sd, ed, fitness_pts, conn)
        metrics_by_id[bid] = m
        prev_metrics_by_type[btype] = m

    result = []
    for row in rows:
        bid, name, btype, sd, ed, notes, created = row
        m = metrics_by_id[bid]
        prev_rows = [r for r in rows if r[2] == btype and r[4] < sd]
        prev_m = metrics_by_id[prev_rows[0][0]] if prev_rows else None
        result.append({
            'id': bid, 'name': name, 'block_type': btype,
            'start_date': sd, 'end_date': ed, 'notes': notes, 'created_at': created,
            'metrics': m, 'delta': _compute_delta(m, prev_m),
        })
    return {"blocks": result, "count": len(result)}


@router.post("/blocks", response_model=schemas.TrainingBlock)
def create_block(body: schemas.TrainingBlockCreate, user_id: str = Depends(get_current_user)):
    conn = get_data_service(user_id)._conn()
    cur = conn.execute(
        "INSERT INTO training_blocks (name, block_type, start_date, end_date, notes) "
        "VALUES (?, ?, ?, ?, ?)",
        (body.name, body.block_type, body.start_date, body.end_date, body.notes)
    )
    conn.commit()
    bid = cur.lastrowid
    row = conn.execute(
        "SELECT id, name, block_type, start_date, end_date, notes, created_at "
        "FROM training_blocks WHERE id = ?", (bid,)
    ).fetchone()
    try:
        fitness_pts = _get_fitness_data(date_from=body.start_date, date_to=body.end_date, conn=conn)
    except Exception:
        fitness_pts = []
    m = _compute_block_metrics(body.start_date, body.end_date, fitness_pts, conn)
    return {
        'id': row[0], 'name': row[1], 'block_type': row[2],
        'start_date': row[3], 'end_date': row[4],
        'notes': row[5], 'created_at': row[6],
        'metrics': m, 'delta': None,
    }


@router.put("/blocks/{block_id}", response_model=schemas.TrainingBlock)
def update_block(
    block_id: int,
    body: schemas.TrainingBlockUpdate,
    user_id: str = Depends(get_current_user),
):
    conn = get_data_service(user_id)._conn()
    existing = conn.execute(
        "SELECT id, name, block_type, start_date, end_date, notes, created_at "
        "FROM training_blocks WHERE id = ?", (block_id,)
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Block not found")

    name       = body.name       if body.name       is not None else existing[1]
    block_type = body.block_type if body.block_type is not None else existing[2]
    start_date = body.start_date if body.start_date is not None else existing[3]
    end_date   = body.end_date   if body.end_date   is not None else existing[4]
    notes      = body.notes      if body.notes      is not None else existing[5]

    conn.execute(
        "UPDATE training_blocks SET name=?, block_type=?, start_date=?, end_date=?, notes=? WHERE id=?",
        (name, block_type, start_date, end_date, notes, block_id)
    )
    conn.commit()
    try:
        fitness_pts = _get_fitness_data(date_from=start_date, date_to=end_date, conn=conn)
    except Exception:
        fitness_pts = []
    m = _compute_block_metrics(start_date, end_date, fitness_pts, conn)
    return {
        'id': block_id, 'name': name, 'block_type': block_type,
        'start_date': start_date, 'end_date': end_date,
        'notes': notes, 'created_at': existing[6],
        'metrics': m, 'delta': None,
    }


@router.delete("/blocks/{block_id}")
def delete_block(block_id: int, user_id: str = Depends(get_current_user)):
    conn = get_data_service(user_id)._conn()
    result = conn.execute("DELETE FROM training_blocks WHERE id = ?", (block_id,))
    conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Block not found")
    return {"status": "deleted"}


# ── Activity deletion (HK-4) ──────────────────────────────────────────────────

@router.delete("/activities/source/{source_id}", status_code=204)
def delete_activity_by_source(source_id: str, user_id: str = Depends(get_current_user)):
    """Delete a HealthKit-sourced activity by its HK UUID. Used by HKAnchoredObjectQuery deletedObjects."""
    from backend.services.apple_health_service import hk_activity_id
    hk_id = hk_activity_id(source_id)

    svc = get_data_service(user_id)
    conn = svc._conn()
    result = conn.execute(
        "DELETE FROM activities WHERE source = 'apple_health' "
        "AND (hk_source_id = ? OR id = ?)",
        (source_id, hk_id),
    )
    conn.commit()
    if result.rowcount > 0:
        svc._invalidate_all_caches()


@router.delete("/activities/{activity_id}", status_code=204)
def delete_activity(activity_id: int, user_id: str = Depends(get_current_user)):
    """Delete any activity by its integer id (user-scoped)."""
    svc = get_data_service(user_id)
    conn = svc._conn()
    result = conn.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
    conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Activity not found")
    svc._invalidate_all_caches()


# ── Route intelligence ────────────────────────────────────────────────────────

@router.post("/routes/build", response_model=schemas.RouteBuildResponse)
def trigger_route_build(
    type: str = Query("Run"),
    threshold: float = Query(0.70),
    user_id: str = Depends(get_current_user),
):
    conn = get_data_service(user_id)._conn()
    result = build_route_clusters(activity_type=type, threshold=threshold, conn=conn)
    return {"status": "ok", **result}


@router.get("/routes", response_model=schemas.RoutesResponse)
def list_routes(
    type: str = Query("Run"),
    user_id: str = Depends(get_current_user),
):
    conn = get_data_service(user_id)._conn()
    status = get_build_status(activity_type=type, conn=conn)
    routes = get_routes(activity_type=type, conn=conn) if status["built"] else []
    return {"routes": routes, "count": len(routes), "built": status["built"]}


@router.get("/routes/{route_id}", response_model=schemas.RouteDetailResponse)
def get_route(route_id: int, user_id: str = Depends(get_current_user)):
    conn = get_data_service(user_id)._conn()
    row = conn.execute("""
        SELECT id, name, activity_type, representative_polyline,
               avg_distance_miles, activity_count, centroid_lat, centroid_lng
        FROM routes WHERE id = ?
    """, (route_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Route not found")

    activities = get_route_activities(route_id, conn=conn)
    paces = [a["pace"] for a in activities if a["pace"] > 0]
    paces_dated = sorted(
        [(a["date"], a["pace"]) for a in activities if a["pace"] > 0],
        key=lambda x: x[0]
    )
    hrs = [a["average_heartrate"] for a in activities if a["average_heartrate"]]

    def _fmt(p):
        if not p or p <= 0: return "—"
        m = int(p); s = round((p - m) * 60)
        return f"{m}:{s:02d}"

    avg_pace = sum(paces) / len(paces) if paces else 0
    best_pace = min(paces) if paces else 0

    pace_trend = None
    if len(paces_dated) >= 4:
        half = len(paces_dated) // 2
        early = [p for _, p in paces_dated[:half]]
        recent = [p for _, p in paces_dated[half:]]
        early_avg  = sum(early) / len(early)
        recent_avg = sum(recent) / len(recent)
        diff = (early_avg - recent_avg) * 60
        pace_trend = {
            "delta_sec_per_mi": round(diff, 1),
            # require a real gain (>3 s/mi faster), matching the pre-rewrite rule
            "improving": diff > 3,
            "early_pace": round(early_avg, 4),
            "recent_pace": round(recent_avg, 4),
        }

    route_obj = {
        "id": row["id"], "name": row["name"],
        "activity_type": row["activity_type"],
        "representative_polyline": row["representative_polyline"],
        "avg_distance_miles": round(float(row["avg_distance_miles"] or 0), 2),
        "activity_count": row["activity_count"],
        "centroid_lat": row["centroid_lat"], "centroid_lng": row["centroid_lng"],
        "avg_pace": round(avg_pace, 4), "avg_pace_str": _fmt(avg_pace),
        "best_pace": round(best_pace, 4), "best_pace_str": _fmt(best_pace),
        "avg_hr": round(sum(hrs) / len(hrs), 1) if hrs else None,
        "first_run": paces_dated[0][0] if paces_dated else None,
        "last_run": paces_dated[-1][0] if paces_dated else None,
        "pace_trend": pace_trend,
        "pace_spark": [{"date": d, "pace": round(p, 4)} for d, p in paces_dated[-20:]],
    }
    return {"route": route_obj, "activities": activities}


@router.put("/routes/{route_id}")
def rename_route_endpoint(
    route_id: int,
    body: dict,
    user_id: str = Depends(get_current_user),
):
    conn = get_data_service(user_id)._conn()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    ok = rename_route(route_id, name, conn=conn)
    if not ok:
        raise HTTPException(status_code=404, detail="Route not found")
    return {"status": "ok"}
