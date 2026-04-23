"""
Route Intelligence API — auto-detected route clusters with performance trends.
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from backend.services.route_service import (
    build_route_clusters, get_routes, get_route_activities,
    rename_route, get_build_status,
)
from backend.models import schemas

router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post("/build", response_model=schemas.RouteBuildResponse)
def trigger_build(
    type: str = Query("Run", description="Activity type to cluster"),
    threshold: float = Query(0.70, description="Route similarity threshold (0–1)"),
):
    """
    Cluster all activities of the given type by GPS route.
    Runs synchronously (typically < 3s for 1000 activities).
    Safe to re-run; clears and rebuilds route tables for this type.
    """
    result = build_route_clusters(activity_type=type, threshold=threshold)
    return {"status": "ok", **result}


@router.get("", response_model=schemas.RoutesResponse)
def list_routes(type: str = Query("Run", description="Activity type")):
    """List all detected routes with aggregate stats and pace trend."""
    status = get_build_status(activity_type=type)
    routes = get_routes(activity_type=type) if status["built"] else []
    return {"routes": routes, "count": len(routes), "built": status["built"]}


@router.get("/{route_id}", response_model=schemas.RouteDetailResponse)
def get_route(route_id: int):
    """Return a single route with its full activity list."""
    from backend.services.database import get_conn
    conn = get_conn()
    row = conn.execute("""
        SELECT id, name, activity_type, representative_polyline,
               avg_distance_miles, activity_count, centroid_lat, centroid_lng
        FROM routes WHERE id = ?
    """, (route_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Route not found")

    activities = get_route_activities(route_id)

    # Build a minimal route object with trend/spark from the activities list
    paces = [a["pace"] for a in activities if a["pace"] > 0]
    paces_dated = sorted(
        [(a["date"], a["pace"]) for a in activities if a["pace"] > 0],
        key=lambda x: x[0]
    )

    def _fmt(p):
        if not p or p <= 0: return "—"
        m = int(p); s = round((p - m) * 60)
        return f"{m}:{s:02d}"

    pace_trend = None
    if len(paces_dated) >= 4:
        n = max(2, len(paces_dated) // 3)
        early = [p for _, p in paces_dated[:n]]
        recent = [p for _, p in paces_dated[-n:]]
        early_avg = sum(early) / len(early)
        recent_avg = sum(recent) / len(recent)
        delta = (recent_avg - early_avg) * 60
        pace_trend = {
            "delta_sec_per_mi": round(delta, 1),
            "improving": delta < -3,
            "early_pace": round(early_avg, 4),
            "recent_pace": round(recent_avg, 4),
        }

    hrs = [a["average_heartrate"] for a in activities if a["average_heartrate"]]

    route = {
        "id":                     row["id"],
        "name":                   row["name"],
        "activity_type":          row["activity_type"],
        "representative_polyline": row["representative_polyline"],
        "avg_distance_miles":     round(row["avg_distance_miles"] or 0, 2),
        "activity_count":         row["activity_count"],
        "centroid_lat":           row["centroid_lat"],
        "centroid_lng":           row["centroid_lng"],
        "avg_pace":               round(sum(paces) / len(paces), 4) if paces else 0,
        "avg_pace_str":           _fmt(sum(paces) / len(paces)) if paces else "—",
        "best_pace":              round(min(paces), 4) if paces else 0,
        "best_pace_str":          _fmt(min(paces)) if paces else "—",
        "avg_hr":                 round(sum(hrs) / len(hrs), 1) if hrs else None,
        "first_run":              paces_dated[0][0] if paces_dated else None,
        "last_run":               paces_dated[-1][0] if paces_dated else None,
        "pace_trend":             pace_trend,
        "pace_spark":             [{"date": d, "pace": p} for d, p in paces_dated[-20:]],
    }

    return {"route": route, "activities": activities}


@router.patch("/{route_id}")
def update_route(route_id: int, body: dict):
    """Rename a route."""
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not rename_route(route_id, name):
        raise HTTPException(status_code=404, detail="Route not found")
    return {"status": "ok"}
