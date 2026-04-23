"""
Activity API routes — CRUD + filtering for activities, splits, and summaries.
Implements Epic 1.4 endpoints.
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from backend.services.data_service import get_data_service
from backend.services.similarity_service import find_similar_activities
from backend.services.pca_service import get_activity_pca
from backend.services.sync_service import get_sync_service
from backend.services.fitness_service import get_fitness_data, _get_hr_params, get_readiness
from backend.services.insight_service import get_insights
from backend.services.race_predictor_service import get_race_predictions
from backend.models import schemas

router = APIRouter(prefix="/api", tags=["activities"])


@router.post("/activities/sync", response_model=schemas.SyncStartResponse)
def sync_activities(deep: bool = Query(False, description="If true, fetches deeper history to fill gaps")):
    """
    Trigger a sync with Strava in the background and return immediately.
    Poll GET /api/activities/sync/status for progress.
    """
    sync_service = get_sync_service()
    result = sync_service.start_sync_background(deep=deep)
    if result.get("status") == "error":
        raise HTTPException(status_code=409, detail=result.get("message"))
    return result


@router.get("/activities/sync/status", response_model=schemas.SyncStatusResponse)
def get_sync_status():
    """
    Poll the status of the currently running (or most recently completed) sync.
    Returns: { status, message, fetched, added, skipped, deep, started_at, error }
    """
    sync_service = get_sync_service()
    return sync_service.get_sync_status()


@router.post("/activities/splits/sync")
def start_splits_backfill(
    limit: Optional[int] = Query(None, description="Max number of activities to backfill (omit for all)"),
    types: Optional[str] = Query(None, description="Comma-separated activity types, e.g. Run,VirtualRun"),
):
    """
    Trigger a background job that fetches splits for all activities that don't have them yet.
    Processes most-recent activities first at ~1 req/sec to stay within Strava rate limits.
    Poll GET /api/activities/splits/sync/status for progress.
    """
    sync_service = get_sync_service()
    type_list = [t.strip() for t in types.split(',')] if types else None
    result = sync_service.start_splits_backfill(limit=limit, types=type_list)
    if result.get("status") == "error":
        raise HTTPException(status_code=409, detail=result.get("message"))
    return result


@router.get("/activities/splits/sync/status")
def get_splits_sync_status():
    """Poll the status of the splits backfill job."""
    sync_service = get_sync_service()
    return sync_service.get_splits_sync_status()


@router.get("/activities", response_model=schemas.ActivityListResponse)
def list_activities(
    type: Optional[str] = Query(None, description="Activity type filter (Run, Ride, Hike)"),
    sport_type: Optional[str] = Query(None, description="Sport type filter"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    min_distance: Optional[float] = Query(None, description="Minimum distance in miles"),
    max_distance: Optional[float] = Query(None, description="Maximum distance in miles"),
    limit: int = Query(50, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """List activities with optional filters."""
    data = get_data_service()
    activities, total = data.get_activities(
        activity_type=type,
        sport_type=sport_type,
        date_from=date_from,
        date_to=date_to,
        min_distance=min_distance,
        max_distance=max_distance,
        limit=limit,
        offset=offset,
    )
    return {
        "activities": activities,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/activities/types", response_model=schemas.ActivityTypesResponse)
def list_activity_types():
    """Return distinct activity types available in the data."""
    data = get_data_service()
    return {"types": data.get_activity_types()}


@router.get("/activities/{activity_id}/insights", response_model=schemas.InsightResponse)
def get_activity_insights(activity_id: int):
    """
    Generate post-workout insights for a single activity.
    Combines PR detection, segment ranking, HR efficiency, split quality,
    pace trend, and volume context into a structured response.
    Some sections may be null if insufficient data is available.
    """
    return get_insights(activity_id)


@router.get("/activities/prs", response_model=schemas.PRsResponse)
def get_recent_prs(
    since: Optional[str] = Query(None, description="ISO date YYYY-MM-DD — only return PRs on or after this date"),
    limit: int = Query(20, ge=1, le=100),
):
    """Return personal records detected from activity detail syncs."""
    data = get_data_service()
    prs = data.get_recent_prs(limit=limit, since=since)
    return {"prs": prs, "count": len(prs)}


@router.get("/activities/{activity_id}", response_model=schemas.ActivityDetail)
def get_activity(activity_id: int):
    """Get full detail for a single activity."""
    data = get_data_service()
    activity = data.get_activity(activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.get("/activities/{activity_id}/splits", response_model=schemas.SplitsResponse)
def get_activity_splits(activity_id: int):
    """Get 0.1-mile splits for an activity."""
    data = get_data_service()
    splits = data.get_splits(activity_id)
    return {"splits": splits, "count": len(splits)}


@router.post("/activities/{activity_id}/sync_details", response_model=schemas.SyncStartResponse)
def sync_activity_details(activity_id: int):
    """Trigger a fetch of granular streams/splits for a specific activity."""
    sync_service = get_sync_service()
    result = sync_service.sync_activity_details(activity_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.get("/activities/{activity_id}/summary", response_model=schemas.SummarySegmentsResponse)
def get_activity_summary(activity_id: int):
    """Get fastest segment summaries for an activity (legacy pre-computed table)."""
    data = get_data_service()
    summary = data.get_summary(activity_id)
    return {"segments": summary, "count": len(summary)}


@router.get("/activities/{activity_id}/fastest_segments", response_model=schemas.RollingFastestSegmentsResponse)
def get_fastest_segments(activity_id: int):
    """
    Compute fastest rolling-window segments from 0.1mi splits.
    Targets: 1mi, 2mi, 5k (3.107mi), 5mi, 10k (6.214mi), half-marathon, marathon.
    Only meaningful for runs with 0.1mi split data.
    """
    data = get_data_service()
    splits = data.get_splits(activity_id)
    if not splits:
        return {"segments": []}

    TARGETS = [
        (1.0,   "1 Mile"),
        (2.0,   "2 Miles"),
        (3.107, "5K"),
        (5.0,   "5 Miles"),
        (6.214, "10K"),
        (13.1,  "Half Marathon"),
        (26.2,  "Marathon"),
    ]

    splits_sorted = sorted(splits, key=lambda s: float(s["split_number"] or 0))
    n = len(splits_sorted)
    total_dist = float(splits_sorted[-1]["total_distance_miles"] or 0) if splits_sorted else 0

    results = []
    for target_miles, label in TARGETS:
        if total_dist < target_miles * 0.95:  # allow 5% short for GPS drift
            continue
        buckets_needed = round(target_miles / 0.1)
        best_time = None
        best_start_mile = None
        best_end_mile = None
        best_hr = None
        for i in range(n - buckets_needed + 1):
            window = splits_sorted[i : i + buckets_needed]
            window_time = sum(float(s["time_seconds"] or 0) for s in window)
            if best_time is None or window_time < best_time:
                best_time = window_time
                last = window[-1]
                end_mi = float(last["total_distance_miles"] or 0)
                best_start_mile = max(0.0, round(end_mi - target_miles, 2))
                best_end_mile   = round(end_mi, 2)
                hrs = [float(s["avg_heartrate"]) for s in window if s.get("avg_heartrate")]
                best_hr = round(sum(hrs) / len(hrs), 1) if hrs else None
        if best_time is not None:
            t = int(best_time)
            h, m, s = t // 3600, (t % 3600) // 60, t % 60
            time_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            pace_sec = best_time / target_miles
            pace_str = f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}/mi"
            results.append({
                "label":          label,
                "distance_miles": target_miles,
                "time_seconds":   round(best_time, 1),
                "time_str":       time_str,
                "pace_str":       pace_str,
                "start_mile":     best_start_mile,
                "end_mile":       best_end_mile,
                "avg_hr":         best_hr,
            })
    return {"segments": results}


@router.get("/activities/{activity_id}/similar", response_model=schemas.SimilarActivitiesResponse)
def get_similar_activities(
    activity_id: int,
    top_n: int = Query(5, ge=1, le=100, description="Number of similar activities to return"),
):
    """Find the most similar activities to the given activity."""
    similar = find_similar_activities(activity_id, top_n=top_n)
    return {"similar": similar, "count": len(similar)}


@router.get("/similarity/pca", response_model=schemas.PCAResponse)
def get_pca_viz(
    type: str = Query("Run", description="Activity type (Run, Ride, Hike)")
):
    """Get PCA coordinates and clustering for all activities of a type."""
    return get_activity_pca(activity_type=type)


@router.post("/activities/compare", response_model=schemas.CompareResponse)
def compare_activities(body: schemas.CompareRequest):
    """Compare multiple activities side-by-side."""
    activity_ids = body.activity_ids
    if not activity_ids or len(activity_ids) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 activity_ids")
    if len(activity_ids) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 activities for comparison")

    data = get_data_service()
    activities = []
    for aid in activity_ids:
        activity = data.get_activity(aid)
        if activity:
            splits = data.get_splits(aid)
            summary = data.get_summary(aid)
            activities.append({
                "activity": activity,
                "splits": splits,
                "summary": summary,
            })
    return {"comparisons": activities, "count": len(activities)}


@router.get("/stats/overview", response_model=schemas.OverviewStats)
def get_overview():
    """Get dashboard overview statistics."""
    data = get_data_service()
    return data.get_overview_stats()


@router.get("/stats/trends", response_model=schemas.TrendsResponse)
def get_trends(
    type: Optional[str] = Query(None, description="Activity type filter"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get time-series trend data for charts."""
    data = get_data_service()
    trends = data.get_trend_data(activity_type=type, date_from=date_from, date_to=date_to)
    return {"data": trends, "count": len(trends)}


@router.get("/stats/calendar", response_model=schemas.CalendarResponse)
def get_calendar(
    months: int = Query(12, ge=1, le=36, description="Number of months to look back"),
):
    """Get daily activity aggregates for the calendar heatmap."""
    data = get_data_service()
    days = data.get_calendar_data(months=months)
    return {"days": days, "months": months}


@router.get("/stats/fitness", response_model=schemas.FitnessResponse)
def get_fitness(
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="End date YYYY-MM-DD"),
):
    """
    Compute daily CTL / ATL / TSB (fitness & fatigue model) using TRIMP.
    CTL = chronic training load (42-day EMA).
    ATL = acute training load (7-day EMA).
    TSB = training stress balance (form) = CTL[prev] - ATL[prev].
    """
    data = get_fitness_data(date_from=date_from, date_to=date_to)
    resting_hr, max_hr = _get_hr_params()
    return {
        "data":        data,
        "count":       len(data),
        "resting_hr":  round(resting_hr, 1),
        "max_hr":      round(max_hr, 1),
    }


@router.get("/stats/readiness", response_model=schemas.ReadinessResponse)
def get_readiness_score():
    """
    Return today's readiness score (0-100) based on current CTL/ATL/TSB.
    Prerequisite: sufficient training history to produce meaningful CTL/ATL.
    """
    data = get_fitness_data()
    if not data:
        return {"score": 50, "zone": "moderate",
                "recommendation": "Not enough data yet — sync more activities.",
                "ctl": 0, "atl": 0, "tsb": 0}
    latest = data[-1]
    return get_readiness(latest["ctl"], latest["atl"], latest["tsb"])


@router.get("/stats/predictions", response_model=schemas.RacePredictionsResponse)
def get_predictions(
    type: str = Query("Run", description="Activity type"),
    days: int = Query(90, description="Look-back window for source efforts (days)"),
):
    """
    Return Riegel-formula race time predictions for 5K, 10K, half, and full marathon.
    Uses the best recent effort at the closest available source distance.
    Adjusts slightly for current training load trend (±2% max).
    """
    preds = get_race_predictions(activity_type=type, days=days)
    return {"predictions": preds, "activity_type": type, "days": days}


@router.get("/stats/best-segments", response_model=schemas.SegmentTrendResponse)
def get_best_segments_trend(
    type: Optional[str] = Query("Run", description="Activity type"),
    distance: float = Query(1.0, description="Target distance in miles"),
    date_from: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    label: Optional[str] = Query(None, description="Legacy label (unused, we use distance)"),
):
    """Get best segments for a specific distance over time."""
    data = get_data_service()
    best_efforts = data.get_best_segments(
        activity_type=type, 
        distance_miles=distance,
        date_from=date_from,
        date_to=date_to
    )
    
    # Map distance back to label for response
    # (Simplified for now)
    label_map = {
        1.0: "1 Mile",
        2.0: "2 Miles",
        3.107: "5K",
        5.0: "5 Miles",
        6.214: "10K",
        13.1: "Half Marathon",
        26.2: "Marathon"
    }
    matching_label = label_map.get(distance, f"{distance} miles")
    
    return {
        "data": best_efforts,
        "distance_miles": distance,
        "label": matching_label
    }


# ── Training Blocks ───────────────────────────────────────────────────────────

from backend.services.database import get_conn
from backend.services.fitness_service import get_fitness_data as _get_fitness_data
import math

BLOCK_COLORS = {
    'base': 'base', 'build': 'build', 'peak': 'peak',
    'taper': 'taper', 'race': 'race',
}

def _compute_block_metrics(start_date: str, end_date: str, fitness_cache: list) -> dict:
    """Aggregate activity metrics and CTL/TSB for a date range."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT type, distance_miles, pace, average_heartrate, total_elevation_gain,
               moving_time_min, date
        FROM activities
        WHERE date >= ? AND date <= ?
    """, (start_date, end_date)).fetchall()

    activities = [dict(zip(
        ['type','distance_miles','pace','average_heartrate','total_elevation_gain','moving_time_min','date'], r
    )) for r in rows]

    total_miles = sum(a['distance_miles'] or 0 for a in activities)
    run_activities = [a for a in activities if a['type'] == 'Run']
    run_count = len(run_activities)
    total_elevation_ft = sum((a['total_elevation_gain'] or 0) * 3.28084 for a in activities)

    # Weekly miles
    from datetime import date as date_cls
    try:
        d0 = date_cls.fromisoformat(start_date)
        d1 = date_cls.fromisoformat(end_date)
        weeks = max(1.0, (d1 - d0).days / 7.0)
    except Exception:
        weeks = 1.0
    avg_weekly_miles = round(total_miles / weeks, 1)

    # Avg run pace
    paces = [a['pace'] for a in run_activities if a['pace'] and a['pace'] > 0]
    avg_pace = round(sum(paces) / len(paces), 4) if paces else None

    # Avg HR (all activity types)
    hrs = [a['average_heartrate'] for a in activities if a['average_heartrate']]
    avg_hr = round(sum(hrs) / len(hrs), 1) if hrs else None

    # CTL/TSB from pre-computed fitness cache
    ctl_start = ctl_end = tsb_start = None
    if fitness_cache:
        # find closest point to start_date
        pts_before_start = [p for p in fitness_cache if p['date'] <= start_date]
        pts_before_end   = [p for p in fitness_cache if p['date'] <= end_date]
        if pts_before_start:
            p = pts_before_start[-1]
            ctl_start  = round(p['ctl'], 1)
            tsb_start  = round(p['tsb'], 1)
        if pts_before_end:
            p = pts_before_end[-1]
            ctl_end = round(p['ctl'], 1)

    ctl_delta = round(ctl_end - ctl_start, 1) if (ctl_start is not None and ctl_end is not None) else None

    return {
        'activity_count': len(activities),
        'run_count': run_count,
        'total_miles': round(total_miles, 1),
        'avg_weekly_miles': avg_weekly_miles,
        'avg_pace': avg_pace,
        'avg_hr': avg_hr,
        'total_elevation_ft': round(total_elevation_ft, 0),
        'ctl_start': ctl_start,
        'ctl_end': ctl_end,
        'ctl_delta': ctl_delta,
        'tsb_start': tsb_start,
    }


def _compute_delta(current: dict, previous: dict) -> dict | None:
    if not previous:
        return None
    delta = {}

    # Pace delta (sec/mi) — negative = faster = improvement
    cp = current.get('avg_pace')
    pp = previous.get('avg_pace')
    if cp and pp:
        diff_sec = (cp - pp) * 60
        sign = '+' if diff_sec > 0 else ''
        m = int(abs(diff_sec) // 60)
        s = int(abs(diff_sec) % 60)
        direction = '↑ faster' if diff_sec < 0 else '↓ slower'
        delta['pace_delta'] = round(diff_sec, 1)
        delta['pace_delta_str'] = f"{sign}{m}:{s:02d}/mi ({direction})"

    # Volume delta %
    cv = current.get('avg_weekly_miles')
    pv = previous.get('avg_weekly_miles')
    if cv and pv and pv > 0:
        delta['volume_delta_pct'] = round(((cv - pv) / pv) * 100, 1)

    # HR delta
    ch = current.get('avg_hr')
    ph = previous.get('avg_hr')
    if ch and ph:
        delta['hr_delta'] = round(ch - ph, 1)

    return delta if delta else None


@router.get("/blocks", response_model=schemas.TrainingBlocksResponse)
def list_blocks():
    """Return all training blocks with aggregated metrics and deltas."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, block_type, start_date, end_date, notes, created_at "
        "FROM training_blocks ORDER BY start_date DESC"
    ).fetchall()

    if not rows:
        return {"blocks": [], "count": 0}

    # Fetch fitness data once for the full date range
    all_dates = [r[3] for r in rows] + [r[4] for r in rows]
    fitness_from = min(all_dates)
    fitness_to   = max(all_dates)
    try:
        fitness_pts = _get_fitness_data(date_from=fitness_from, date_to=fitness_to)
    except Exception:
        fitness_pts = []

    # Build metrics for each block; track previous per type for delta
    prev_metrics_by_type: dict = {}
    blocks_asc = list(reversed(rows))  # oldest first for delta chaining
    metrics_by_id = {}

    for row in blocks_asc:
        bid, name, btype, sd, ed, notes, created = row
        m = _compute_block_metrics(sd, ed, fitness_pts)
        metrics_by_id[bid] = m
        prev_metrics_by_type[btype] = m

    result = []
    for row in rows:  # back to DESC for response
        bid, name, btype, sd, ed, notes, created = row
        m = metrics_by_id[bid]

        # Find the previous block of same type (earlier date)
        prev_rows = [r for r in rows if r[2] == btype and r[4] < sd]
        prev_m = metrics_by_id[prev_rows[0][0]] if prev_rows else None
        delta = _compute_delta(m, prev_m)

        result.append({
            'id': bid, 'name': name, 'block_type': btype,
            'start_date': sd, 'end_date': ed,
            'notes': notes, 'created_at': created,
            'metrics': m, 'delta': delta,
        })

    return {"blocks": result, "count": len(result)}


@router.post("/blocks", response_model=schemas.TrainingBlock)
def create_block(body: schemas.TrainingBlockCreate):
    conn = get_conn()
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

    fitness_pts = []
    try:
        fitness_pts = _get_fitness_data(date_from=body.start_date, date_to=body.end_date)
    except Exception:
        pass

    m = _compute_block_metrics(body.start_date, body.end_date, fitness_pts)
    return {
        'id': row[0], 'name': row[1], 'block_type': row[2],
        'start_date': row[3], 'end_date': row[4],
        'notes': row[5], 'created_at': row[6],
        'metrics': m, 'delta': None,
    }


@router.put("/blocks/{block_id}", response_model=schemas.TrainingBlock)
def update_block(block_id: int, body: schemas.TrainingBlockUpdate):
    conn = get_conn()
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

    fitness_pts = []
    try:
        fitness_pts = _get_fitness_data(date_from=start_date, date_to=end_date)
    except Exception:
        pass

    m = _compute_block_metrics(start_date, end_date, fitness_pts)
    return {
        'id': block_id, 'name': name, 'block_type': block_type,
        'start_date': start_date, 'end_date': end_date,
        'notes': notes, 'created_at': existing[6],
        'metrics': m, 'delta': None,
    }


@router.delete("/blocks/{block_id}")
def delete_block(block_id: int):
    conn = get_conn()
    result = conn.execute("DELETE FROM training_blocks WHERE id = ?", (block_id,))
    conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Block not found")
    return {"status": "deleted"}
