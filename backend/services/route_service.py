"""
Route Intelligence service.

Clusters outdoor activities by GPS route using greedy similarity matching,
then computes per-route performance trends (pace, HR, best time).

Algorithm
---------
1. Load all non-trainer activities of the requested type that have polylines.
2. Sort by date DESC (newest first → representative = most recent run on route).
3. For each activity, compute route_similarity against every known route centroid.
   - Start proximity (weight 0.4): 1.0 if < 0.15mi, 0.5 if < 0.4mi, else 0
   - Waypoint match (weight 0.6): 1.0 if avg dist < 0.15mi, 0.5 if < 0.4mi, else 0
4. If best match ≥ threshold (default 0.70), assign; otherwise create new route.
5. Route representative is always the most-recently-dated activity in the cluster.
6. Routes with < min_activities (default 2) are discarded as noise.

Performance
-----------
With 1 000 activities and 30 routes, total waypoint comparisons ≈ 1 000 × 30 × 8 = 240 K.
At ~1 μs each that is < 1 second. Cached in memory after first build.
"""

import logging
import math
from collections import defaultdict, Counter
from datetime import date, timedelta
from typing import Optional

import polyline as polyline_lib
import numpy as np

from backend.services.database import get_conn

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

WAYPOINTS      = 10        # number of distributed waypoints per route
THRESHOLD      = 0.70      # similarity score to assign to existing route
MIN_ACTIVITIES = 2         # discard routes with fewer activities
EARTH_RADIUS   = 3959.0    # miles


# ── Geometry helpers ─────────────────────────────────────────────────────────

def _haversine(lat1, lng1, lat2, lng2) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return EARTH_RADIUS * 2 * math.asin(math.sqrt(a))


def _extract_waypoints(polyline_str: str, n: int = WAYPOINTS):
    """Decode polyline and return n evenly-spaced (lat, lng) tuples."""
    if not polyline_str or not isinstance(polyline_str, str):
        return []
    try:
        pts = polyline_lib.decode(polyline_str)
        if len(pts) < 2:
            return pts
        indices = np.linspace(0, len(pts) - 1, n).astype(int)
        return [pts[i] for i in indices]
    except Exception:
        return []


def _route_similarity(wp1, start1, wp2, start2) -> float:
    """
    Score 0-1 measuring how well two routes overlap.
    wp1/wp2: lists of (lat, lng) waypoints (same length).
    start1/start2: (lat, lng) tuples for the start points.
    """
    score = 0.0

    # Start proximity (weight 0.4)
    if start1 and start2:
        d = _haversine(start1[0], start1[1], start2[0], start2[1])
        if d < 0.15:
            score += 0.4
        elif d < 0.4:
            score += 0.2

    # Waypoint proximity (weight 0.6)
    if wp1 and wp2 and len(wp1) == len(wp2):
        dists = [_haversine(a[0], a[1], b[0], b[1]) for a, b in zip(wp1, wp2)]
        avg = sum(dists) / len(dists)
        if avg < 0.15:
            score += 0.6
        elif avg < 0.40:
            score += 0.30
        elif avg < 0.70:
            score += 0.10

    return min(score, 1.0)


# ── Auto-name helper ─────────────────────────────────────────────────────────

def _auto_name(activity_names: list) -> str:
    """Pick the most common non-generic activity name for a route cluster."""
    generic = {'morning run', 'afternoon run', 'evening run', 'lunch run',
               'easy run', 'run', 'morning ride', 'afternoon ride', 'evening ride'}
    non_generic = [n for n in activity_names if n.lower().strip() not in generic]
    if non_generic:
        most_common = Counter(non_generic).most_common(1)[0][0]
        return most_common
    return Counter(activity_names).most_common(1)[0][0] if activity_names else 'Route'


# ── Core clustering ──────────────────────────────────────────────────────────

def build_route_clusters(
    activity_type: str = 'Run',
    threshold: float = THRESHOLD,
    min_activities: int = MIN_ACTIVITIES,
) -> dict:
    """
    Cluster all outdoor activities of `activity_type` by GPS route.
    Rebuilds from scratch; writes results to `routes` + `route_activities` tables.
    Returns a summary dict.
    """
    conn = get_conn()

    # Load activities with polylines (exclude trainer / manual / no polyline)
    rows = conn.execute("""
        SELECT id, name, date, distance_miles, pace, average_heartrate,
               map_polyline, start_latlng, trainer
        FROM activities
        WHERE type = ?
          AND map_polyline IS NOT NULL
          AND map_polyline != ''
          AND map_polyline != 'nan'
          AND (trainer IS NULL OR trainer = 0)
        ORDER BY date DESC
    """, (activity_type,)).fetchall()

    if not rows:
        return {"routes_found": 0, "activities_clustered": 0}

    # Pre-compute waypoints and start points
    acts = []
    for r in rows:
        wp = _extract_waypoints(r["map_polyline"])
        if len(wp) < 4:
            continue
        start = wp[0]
        acts.append({
            "id":           r["id"],
            "name":         r["name"] or "",
            "date":         r["date"] or "",
            "distance":     float(r["distance_miles"] or 0),
            "pace":         float(r["pace"] or 0),
            "hr":           float(r["average_heartrate"] or 0) or None,
            "waypoints":    wp,
            "start":        start,
        })

    # Greedy clustering
    # Each cluster: { representative_wp, representative_start, members: [...] }
    clusters = []

    for act in acts:
        best_score = 0.0
        best_idx   = -1

        for ci, cluster in enumerate(clusters):
            score = _route_similarity(
                act["waypoints"], act["start"],
                cluster["rep_wp"],  cluster["rep_start"],
            )
            if score > best_score:
                best_score = score
                best_idx   = ci

        if best_score >= threshold:
            clusters[best_idx]["members"].append((act, best_score))
        else:
            # New route — this activity becomes the representative
            clusters.append({
                "rep_wp":    act["waypoints"],
                "rep_start": act["start"],
                "rep_act":   act,
                "members":   [(act, 1.0)],
            })

    # Filter noise
    clusters = [c for c in clusters if len(c["members"]) >= min_activities]

    # Clear old route data and rebuild
    conn.execute("DELETE FROM route_activities WHERE route_id IN (SELECT id FROM routes WHERE activity_type = ?)", (activity_type,))
    conn.execute("DELETE FROM routes WHERE activity_type = ?", (activity_type,))
    conn.commit()

    routes_inserted = 0
    activities_clustered = 0

    for cluster in clusters:
        members   = cluster["members"]
        rep       = cluster["rep_act"]
        all_acts  = [m[0] for m in members]

        name          = _auto_name([a["name"] for a in all_acts])
        avg_dist      = round(sum(a["distance"] for a in all_acts) / len(all_acts), 2)
        centroid_lat  = rep["start"][0]
        centroid_lng  = rep["start"][1]
        activity_count = len(members)

        cur = conn.execute("""
            INSERT INTO routes
                (name, activity_type, representative_polyline, avg_distance_miles,
                 activity_count, centroid_lat, centroid_lng)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, activity_type, rep["waypoints"] and cluster["rep_act"].get("map_polyline_raw", None),
              avg_dist, activity_count, centroid_lat, centroid_lng))

        route_id = cur.lastrowid

        for act, score in members:
            conn.execute("""
                INSERT OR REPLACE INTO route_activities (route_id, activity_id, similarity_score)
                VALUES (?, ?, ?)
            """, (route_id, act["id"], round(score, 4)))
            activities_clustered += 1

        routes_inserted += 1

    conn.commit()

    # Store the actual polyline strings (need separate query since we need the original string)
    _store_representative_polylines(conn, acts, clusters)

    logger.info(f"Route clustering: {routes_inserted} routes from {activities_clustered} activities (type={activity_type})")
    return {"routes_found": routes_inserted, "activities_clustered": activities_clustered}


def _store_representative_polylines(conn, acts, clusters):
    """
    We can't pass the polyline string through the waypoints dict easily,
    so fetch the original polyline from the DB for each representative activity.
    """
    if not clusters:
        return
    rep_ids = [c["rep_act"]["id"] for c in clusters]
    if not rep_ids:
        return

    placeholders = ",".join("?" * len(rep_ids))
    poly_rows = conn.execute(
        f"SELECT id, map_polyline FROM activities WHERE id IN ({placeholders})",
        rep_ids
    ).fetchall()
    poly_map = {r[0]: r[1] for r in poly_rows}

    # Get the route IDs in insertion order by matching back via centroid
    routes = conn.execute(
        "SELECT id, centroid_lat, centroid_lng FROM routes ORDER BY id DESC LIMIT ?",
        (len(clusters),)
    ).fetchall()

    # Match each route to its cluster by centroid
    for route in routes:
        rid, clat, clng = route
        for cluster in clusters:
            rep = cluster["rep_act"]
            if abs(rep["start"][0] - clat) < 0.0001 and abs(rep["start"][1] - clng) < 0.0001:
                polyline_str = poly_map.get(rep["id"])
                if polyline_str:
                    conn.execute(
                        "UPDATE routes SET representative_polyline = ? WHERE id = ?",
                        (polyline_str, rid)
                    )
                break

    conn.commit()


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_routes(activity_type: str = 'Run') -> list:
    """Return all routes with aggregate stats and recent pace trend."""
    conn = get_conn()

    routes = conn.execute("""
        SELECT id, name, activity_type, representative_polyline,
               avg_distance_miles, activity_count, centroid_lat, centroid_lng,
               created_at
        FROM routes
        WHERE activity_type = ?
        ORDER BY activity_count DESC
    """, (activity_type,)).fetchall()

    result = []
    for r in routes:
        route_id = r["id"]

        # Aggregate metrics for activities on this route
        agg = conn.execute("""
            SELECT
                COUNT(*)                         AS cnt,
                AVG(a.pace)                      AS avg_pace,
                MIN(a.pace)                      AS best_pace,
                AVG(a.average_heartrate)         AS avg_hr,
                MIN(a.date)                      AS first_run,
                MAX(a.date)                      AS last_run
            FROM route_activities ra
            JOIN activities a ON a.id = ra.activity_id
            WHERE ra.route_id = ?
        """, (route_id,)).fetchone()

        # Pace trend: compare last 5 runs vs first 5 runs (if enough data)
        pace_rows = conn.execute("""
            SELECT a.date, a.pace
            FROM route_activities ra
            JOIN activities a ON a.id = ra.activity_id
            WHERE ra.route_id = ? AND a.pace > 0
            ORDER BY a.date ASC
        """, (route_id,)).fetchall()

        pace_trend = None
        if len(pace_rows) >= 4:
            n = max(2, len(pace_rows) // 3)
            early_avg = sum(p["pace"] for p in pace_rows[:n]) / n
            recent_avg = sum(p["pace"] for p in pace_rows[-n:]) / n
            delta_sec = (recent_avg - early_avg) * 60  # positive = slower, negative = faster
            pace_trend = {
                "delta_sec_per_mi": round(delta_sec, 1),
                "improving": delta_sec < -3,   # faster by > 3 sec/mi
                "early_pace": round(early_avg, 4),
                "recent_pace": round(recent_avg, 4),
            }

        # Spark data (last 20 pace values for mini chart)
        spark = [{"date": p["date"], "pace": round(p["pace"], 4)} for p in pace_rows[-20:]]

        def _fmt_pace(pace_min_mi):
            if not pace_min_mi or pace_min_mi <= 0:
                return "—"
            m = int(pace_min_mi)
            s = round((pace_min_mi - m) * 60)
            return f"{m}:{s:02d}"

        result.append({
            "id":                     route_id,
            "name":                   r["name"],
            "activity_type":          r["activity_type"],
            "representative_polyline": r["representative_polyline"],
            "avg_distance_miles":     round(r["avg_distance_miles"] or 0, 2),
            "activity_count":         r["activity_count"],
            "centroid_lat":           r["centroid_lat"],
            "centroid_lng":           r["centroid_lng"],
            "avg_pace":               round(agg["avg_pace"] or 0, 4),
            "avg_pace_str":           _fmt_pace(agg["avg_pace"]),
            "best_pace":              round(agg["best_pace"] or 0, 4),
            "best_pace_str":          _fmt_pace(agg["best_pace"]),
            "avg_hr":                 round(agg["avg_hr"], 1) if agg["avg_hr"] else None,
            "first_run":              agg["first_run"],
            "last_run":               agg["last_run"],
            "pace_trend":             pace_trend,
            "pace_spark":             spark,
        })

    return result


def get_route_activities(route_id: int) -> list:
    """Return all activities on a route, ordered by date."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            a.id, a.name, a.date, a.distance_miles, a.pace,
            a.average_heartrate, a.total_elevation_gain,
            a.moving_time_min, ra.similarity_score
        FROM route_activities ra
        JOIN activities a ON a.id = ra.activity_id
        WHERE ra.route_id = ?
        ORDER BY a.date DESC
    """, (route_id,)).fetchall()

    def _fmt_pace(p):
        if not p or p <= 0: return "—"
        m = int(p); s = round((p - m) * 60)
        return f"{m}:{s:02d}"

    def _fmt_time(mins):
        if not mins: return "—"
        h = int(mins // 60); m = int(mins % 60)
        return f"{h}h {m}m" if h else f"{m}m"

    return [{
        "id":               r["id"],
        "name":             r["name"],
        "date":             r["date"],
        "distance_miles":   round(float(r["distance_miles"] or 0), 2),
        "pace":             round(float(r["pace"] or 0), 4),
        "pace_str":         _fmt_pace(r["pace"]),
        "average_heartrate": round(float(r["average_heartrate"]), 1) if r["average_heartrate"] else None,
        "total_elevation_gain": float(r["total_elevation_gain"] or 0),
        "duration_str":     _fmt_time(r["moving_time_min"]),
        "similarity_score": round(float(r["similarity_score"] or 0), 3),
    } for r in rows]


def rename_route(route_id: int, name: str) -> bool:
    conn = get_conn()
    result = conn.execute(
        "UPDATE routes SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (name, route_id)
    )
    conn.commit()
    return result.rowcount > 0


def get_build_status(activity_type: str = 'Run') -> dict:
    """Return how many routes exist and when they were last built."""
    conn = get_conn()
    row = conn.execute("""
        SELECT COUNT(*) as cnt, MAX(created_at) as last_built
        FROM routes WHERE activity_type = ?
    """, (activity_type,)).fetchone()
    return {
        "route_count": row["cnt"],
        "last_built":  row["last_built"],
        "built":       row["cnt"] > 0,
    }
