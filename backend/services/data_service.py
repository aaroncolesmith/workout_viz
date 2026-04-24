"""
Data service — loads, processes, and serves activity/split/summary data.
Backed by SQLite (via backend.services.database) instead of raw CSV files.

Storage:
  - SQLite is the source of truth for all raw and derived data.
  - CSV files are still written by SyncService for backward-compatibility
    with any external tooling, but DataService no longer reads from them.

Analytics:
  - pandas is only used for in-process analytics (overview stats, trend data,
    calendar aggregation, rolling averages for PCA/similarity consumption).
  - All simple list/filter/detail reads go straight to SQL.

Caching (P1-4):
  - A lightweight TTL in-memory cache (CachingLayer) wraps the two most
    expensive read paths: PCA vectors and similarity results.
  - The cache is automatically invalidated whenever add_activities() or
    update_activities() writes new data.
"""
import os
import ast
import math
import time as _time
import threading
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any, Union

import numpy as np
import pandas as pd

from backend.services.database import init_db, get_conn

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent.parent / "data"))
DB_PATH  = Path(os.getenv("DB_PATH",   Path(__file__).parent.parent / "workouts.db"))

# ── TTL cache ─────────────────────────────────────────────────────────────────

class _TTLCache:
    """
    Thread-safe in-memory TTL cache keyed by arbitrary strings.
    Entries expire after `ttl_seconds`.  A full flush is available for
    write-side invalidation.
    """
    def __init__(self, ttl_seconds: int = 300):
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, val = entry
            if _time.monotonic() - ts > self._ttl:
                del self._store[key]
                return None
            return val

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (_time.monotonic(), value)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def flush(self) -> None:
        """Evict everything — called on any write."""
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        with self._lock:
            now = _time.monotonic()
            live = sum(1 for ts, _ in self._store.values() if now - ts <= self._ttl)
            return {"total_entries": len(self._store), "live_entries": live, "ttl_seconds": self._ttl}


# ── DataService ────────────────────────────────────────────────────────────────

class DataService:
    """
    Singleton-style data service backed by SQLite.

    Public API is identical to the old CSV-based DataService so all callers
    (API routes, SyncService, PCA service, similarity service) continue to work
    without changes.
    """

    # Cache TTLs
    _OVERVIEW_TTL   = 60    # overview recomputed at most once per minute
    _TRENDS_TTL     = 120   # trend data: 2 min
    _CALENDAR_TTL   = 120
    _ANALYTICS_TTL  = 300   # PCA / similarity: 5 min (expensive)

    def __init__(self):
        t0 = _time.perf_counter()
        # Ensure DB is initialised
        init_db(DB_PATH)
        self._write_lock = threading.Lock()

        # Per-topic caches
        self._overview_cache  = _TTLCache(self._OVERVIEW_TTL)
        self._trends_cache    = _TTLCache(self._TRENDS_TTL)
        self._calendar_cache  = _TTLCache(self._CALENDAR_TTL)
        self._analytics_cache = _TTLCache(self._ANALYTICS_TTL)  # PCA, similarity

        elapsed_ms = (_time.perf_counter() - t0) * 1000
        n = get_conn().execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        logger.info(f"DataService ready — {n} activities in SQLite ({elapsed_ms:.0f}ms)")

    # ── Write helpers ──────────────────────────────────────────────────────────

    def _invalidate_all_caches(self):
        self._overview_cache.flush()
        self._trends_cache.flush()
        self._calendar_cache.flush()
        self._analytics_cache.flush()

    def get_latest_activity_timestamp(self) -> Optional[datetime]:
        row = get_conn().execute(
            "SELECT MAX(start_date) FROM activities"
        ).fetchone()
        if not row or not row[0]:
            return None
        try:
            return datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        except Exception:
            return None

    # ── add_activities ─────────────────────────────────────────────────────────

    def add_activities(self, new_activities: List[dict]) -> int:
        if not new_activities:
            return 0

        inserted = 0
        conn = get_conn()
        with self._write_lock:
            for act in new_activities:
                act_id = act.get("id")
                if not act_id:
                    continue
                params = self._activity_to_db_params(act)
                try:
                    conn.execute(
                        self._upsert_sql(),
                        params,
                    )
                    if conn.execute("SELECT changes()").fetchone()[0] > 0:
                        inserted += 1
                except Exception as e:
                    logger.warning(f"Failed to upsert activity {act_id}: {e}")
            conn.commit()

        # Also keep CSV in sync for legacy tooling / SyncService
        if inserted:
            self._also_write_csv()

        self._invalidate_all_caches()
        return inserted

    def add_summaries(self, summaries: List[dict]):
        if not summaries:
            return
        conn = get_conn()
        with self._write_lock:
            for s in summaries:
                conn.execute("""
                    INSERT INTO summaries (
                        activity_id, activity_name, distance_miles,
                        fastest_time_seconds, fastest_time_minutes,
                        start_mile, end_mile, avg_heartrate_fastest,
                        elevation_gain_fastest_meters
                    ) VALUES (
                        :activity_id, :activity_name, :distance_miles,
                        :fastest_time_seconds, :fastest_time_minutes,
                        :start_mile, :end_mile, :avg_heartrate_fastest,
                        :elevation_gain_fastest_meters
                    )
                """, {
                    "activity_id":                   int(s["activity_id"]),
                    "activity_name":                 s.get("activity_name", ""),
                    "distance_miles":                self._sf(s["distance_miles"]),
                    "fastest_time_seconds":          self._sf(s["fastest_time_seconds"]),
                    "fastest_time_minutes":          s.get("fastest_time_minutes", ""),
                    "start_mile":                    self._sf(s["start_mile"]),
                    "end_mile":                      self._sf(s["end_mile"]),
                    "avg_heartrate_fastest":         self._sf(s["avg_heartrate_fastest"]),
                    "elevation_gain_fastest_meters": self._sf(s["elevation_gain_fastest_meters"]),
                })
            conn.commit()

    def compute_and_save_summaries(self, activity_id: int):
        """Compute fastest segments from splits and save to summaries table."""
        splits = self.get_splits(activity_id)
        if not splits:
            return
        
        # We reuse the logic that was previously in API layer
        # but adapt it to save to DB.
        TARGETS = [
            (0.25,  "1/4 Mile"),
            (0.5,   "1/2 Mile"),
            (1.0,   "1 Mile"),
            (2.0,   "2 Miles"),
            (3.107, "5K"),
            (5.0,   "5 Miles"),
            (6.214, "10K"),
            (10.0,  "10 Miles"),
            (13.1,  "Half Marathon"),
            (25.0,  "25 Miles"),
            (26.2,  "Marathon"),
            (50.0,  "50 Miles"),
        ]
        
        splits_sorted = sorted(splits, key=lambda s: float(s["split_number"] or 0))
        n = len(splits_sorted)
        total_dist = float(splits_sorted[-1]["total_distance_miles"] or 0) if splits_sorted else 0
        activity_name = splits_sorted[0].get("activity_name", "Activity")

        summaries = []
        for target_miles, label in TARGETS:
            if total_dist < target_miles * 0.95:
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
                
                summaries.append({
                    "activity_id": activity_id,
                    "activity_name": activity_name,
                    "distance_miles": target_miles,
                    "fastest_time_seconds": round(best_time, 1),
                    "fastest_time_minutes": time_str,
                    "start_mile": best_start_mile,
                    "end_mile": best_end_mile,
                    "avg_heartrate_fastest": best_hr,
                    "elevation_gain_fastest_meters": sum(float(s["elevation_gain_meters"] or 0) for s in splits_sorted[int(best_start_mile/0.1):int(best_end_mile/0.1)]) # approximation
                })

        if summaries:
            # First clear existing summaries for this activity
            conn = get_conn()
            with self._write_lock:
                conn.execute("DELETE FROM summaries WHERE activity_id = ?", (activity_id,))
            self.add_summaries(summaries)
            self.detect_prs_for_activity(activity_id)

    def detect_prs_for_activity(self, activity_id: int) -> List[dict]:
        """
        Compare freshly-computed summaries for activity_id against the
        all-time best for each distance (same activity type).
        Inserts a row into pr_events for every distance that beats the
        previous record.  Returns the list of new PR dicts.
        """
        conn = get_conn()
        # Get the activity's type and date
        act_row = conn.execute(
            "SELECT type, date, name FROM activities WHERE id = ?", (activity_id,)
        ).fetchone()
        if not act_row:
            return []

        act_type = act_row["type"]
        act_date = act_row["date"]
        act_name = act_row["name"] or "Activity"

        # Get this activity's summaries
        my_summaries = conn.execute("""
            SELECT s.distance_miles, s.fastest_time_seconds
            FROM   summaries s
            WHERE  s.activity_id = ?
        """, (activity_id,)).fetchall()

        if not my_summaries:
            return []

        new_prs = []
        with self._write_lock:
            for row in my_summaries:
                dist   = float(row["distance_miles"])
                my_t   = float(row["fastest_time_seconds"])

                # Best time for this distance across all OTHER activities of same type
                prev_row = conn.execute("""
                    SELECT MIN(s.fastest_time_seconds) AS best_t
                    FROM   summaries s
                    JOIN   activities a ON a.id = s.activity_id
                    WHERE  a.type = ?
                      AND  s.distance_miles = ?
                      AND  s.activity_id   != ?
                """, (act_type, dist, activity_id)).fetchone()

                prev_best = float(prev_row["best_t"]) if prev_row and prev_row["best_t"] else None

                # Only count as PR if we beat the previous best (or it's the first effort)
                if prev_best is None or my_t < prev_best:
                    # Map distance to label
                    label_map = {
                        1.0:   "1 Mile",
                        2.0:   "2 Miles",
                        3.107: "5K",
                        5.0:   "5 Miles",
                        6.214: "10K",
                        13.1:  "Half Marathon",
                        26.2:  "Marathon",
                    }
                    label = min(label_map, key=lambda k: abs(k - dist))
                    label = label_map[label]

                    t = int(my_t)
                    h, m, s = t // 3600, (t % 3600) // 60, t % 60
                    time_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                    pace_sec = my_t / dist
                    pace_str = f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}/mi"

                    # Delete any existing PR for this activity+distance (re-detection)
                    conn.execute("""
                        DELETE FROM pr_events
                        WHERE activity_id = ? AND distance_miles = ?
                    """, (activity_id, dist))

                    conn.execute("""
                        INSERT INTO pr_events (
                            activity_id, activity_name, activity_type, date,
                            distance_label, distance_miles,
                            time_seconds, time_str, pace_str,
                            previous_best_seconds
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        activity_id, act_name, act_type, act_date,
                        label, dist,
                        my_t, time_str, pace_str,
                        prev_best,
                    ))

                    new_prs.append({
                        "activity_id":     activity_id,
                        "activity_name":   act_name,
                        "activity_type":   act_type,
                        "date":            act_date,
                        "distance_label":  label,
                        "distance_miles":  dist,
                        "time_seconds":    my_t,
                        "time_str":        time_str,
                        "pace_str":        pace_str,
                        "previous_best_seconds": prev_best,
                    })

            if new_prs:
                conn.commit()
                logger.info(f"Detected {len(new_prs)} PR(s) for activity {activity_id}")

        return new_prs

    def get_recent_prs(self, limit: int = 20, since: Optional[str] = None) -> List[dict]:
        """Return recent PR events, most recent first."""
        conn = get_conn()
        where = "WHERE 1=1"
        params: list = []
        if since:
            where += " AND date >= ?"
            params.append(since)
        rows = conn.execute(f"""
            SELECT p.*, a.type as activity_type
            FROM   pr_events p
            LEFT JOIN activities a ON a.id = p.activity_id
            {where}
            ORDER  BY p.date DESC, p.detected_at DESC
            LIMIT  ?
        """, params + [limit]).fetchall()
        return [dict(r) for r in rows]

    def update_activities(self, updated_list: List[dict]):
        if not updated_list:
            return
        conn = get_conn()
        with self._write_lock:
            for act in updated_list:
                act_id = act.get("id")
                if not act_id:
                    continue
                # Build SET clause from present keys only
                settable = {k: v for k, v in act.items() if k != "id"}
                if not settable:
                    continue
                cols = ", ".join(f"{k} = :{k}" for k in settable)
                params = {k: self._coerce(k, v) for k, v in settable.items()}
                params["id"] = act_id
                try:
                    conn.execute(f"UPDATE activities SET {cols} WHERE id = :id", params)
                except Exception as e:
                    logger.warning(f"Failed to update activity {act_id}: {e}")
            conn.commit()
        self._also_write_csv()
        self._invalidate_all_caches()

    def add_splits(self, new_splits: List[dict]):
        if not new_splits:
            return
        act_id = new_splits[0].get("activity_id")
        conn = get_conn()
        with self._write_lock:
            # Delete existing splits for this activity — same behaviour as CSV version
            if act_id:
                conn.execute("DELETE FROM splits WHERE activity_id = ?", (act_id,))
            for sp in new_splits:
                aid = sp.get("activity_id") or act_id
                conn.execute("""
                    INSERT INTO splits (
                        activity_id, activity_name, split_number, time_seconds, time_minutes,
                        max_heartrate, avg_heartrate, avg_cadence, avg_velocity,
                        elevation_gain_meters, total_distance_miles, date
                    ) VALUES (
                        :activity_id, :activity_name, :split_number, :time_seconds, :time_minutes,
                        :max_heartrate, :avg_heartrate, :avg_cadence, :avg_velocity,
                        :elevation_gain_meters, :total_distance_miles, :date
                    )
                """, {
                    "activity_id": aid,
                    "activity_name": sp.get("activity_name", ""),
                    "split_number":  self._sf(sp.get("split_number") or sp.get("0.1_mile")),
                    "time_seconds":  self._sf(sp.get("time_seconds")),
                    "time_minutes":  str(sp.get("time_minutes", "") or ""),
                    "max_heartrate": self._sf(sp.get("max_heartrate")),
                    "avg_heartrate": self._sf(sp.get("avg_heartrate")),
                    "avg_cadence":   self._sf(sp.get("avg_cadence")),
                    "avg_velocity":  self._sf(sp.get("avg_velocity")),
                    "elevation_gain_meters":   self._sf(sp.get("elevation_gain_meters")),
                    "total_distance_miles":    self._sf(sp.get("total_distance_miles")),
                    "date": sp.get("date"),
                })
            conn.commit()
        
        # Automatically compute and save summaries
        if act_id:
            self.compute_and_save_summaries(act_id)

    # ── Read: activities ───────────────────────────────────────────────────────

    def get_activities(
        self,
        activity_type: Optional[str] = None,
        sport_type:    Optional[str] = None,
        date_from:     Optional[str] = None,
        date_to:       Optional[str] = None,
        min_distance:  Optional[float] = None,
        max_distance:  Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[dict], int]:
        """Return filtered activities as (list_of_dicts, total_count)."""
        where, params = self._build_where(
            activity_type=activity_type,
            sport_type=sport_type,
            date_from=date_from,
            date_to=date_to,
            min_distance=min_distance,
            max_distance=max_distance,
        )
        conn = get_conn()
        total = conn.execute(
            f"SELECT COUNT(*) FROM activities{where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM activities{where} ORDER BY date DESC, start_date DESC "
            f"LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [self._row_to_summary(r) for r in rows], total

    def get_activity(self, activity_id: int) -> Optional[dict]:
        row = get_conn().execute(
            "SELECT * FROM activities WHERE id = ?", (activity_id,)
        ).fetchone()
        return self._row_to_detail(row) if row else None

    def get_splits(self, activity_id: int) -> List[dict]:
        rows = get_conn().execute(
            "SELECT * FROM splits WHERE activity_id = ? ORDER BY split_number ASC",
            (activity_id,),
        ).fetchall()
        return [self._row_to_split(r) for r in rows]

    def get_summary(self, activity_id: int) -> List[dict]:
        rows = get_conn().execute(
            "SELECT * FROM summaries WHERE activity_id = ?", (activity_id,)
        ).fetchall()
        return [self._row_to_summary_record(r) for r in rows]

    def get_best_segments(
        self,
        activity_type: Optional[str] = None,
        distance_miles: Optional[float] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        label: Optional[str] = None,
    ) -> List[dict]:
        """
        Get best segments over time for a given distance.
        Joins summaries with activities to get dates.
        """
        clauses = ["s.activity_id = a.id"]
        params = []
        if activity_type:
            clauses.append("a.type = ?")
            params.append(activity_type)
        if distance_miles is not None:
            clauses.append("ABS(s.distance_miles - ?) < 0.01")
            params.append(distance_miles)
        if date_from:
            clauses.append("a.date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("a.date <= ?")
            params.append(date_to)
        
        where = " WHERE " + " AND ".join(clauses)
        
        query = f"""
            SELECT 
                a.date, a.id as activity_id, a.name as activity_name,
                s.distance_miles, s.fastest_time_seconds, s.fastest_time_minutes,
                s.avg_heartrate_fastest
            FROM summaries s, activities a
            {where}
            ORDER BY a.date ASC
        """
        
        rows = get_conn().execute(query, params).fetchall()
        
        result = []
        for r in rows:
            pace_sec = r["fastest_time_seconds"] / r["distance_miles"]
            pace_str = f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}/mi"
            result.append({
                "date": r["date"],
                "activity_id": r["activity_id"],
                "activity_name": r["activity_name"],
                "time_seconds": r["fastest_time_seconds"],
                "time_str": r["fastest_time_minutes"],
                "pace_str": pace_str,
                "avg_heartrate": r["avg_heartrate_fastest"],
            })
        return result

    # ── Read: derived / aggregated ─────────────────────────────────────────────

    def get_overview_stats(self) -> dict:
        cached = self._overview_cache.get("overview")
        if cached is not None:
            return cached

        conn = get_conn()
        total = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        if total == 0:
            result = {
                "total_activities": 0, "total_miles": 0.0, "total_hours": 0.0,
                "avg_pace": None, "avg_heartrate": None, "activity_types": {},
                "recent_activities": [], "strava_total_count": 0,
            }
            self._overview_cache.set("overview", result)
            return result

        totals = conn.execute("""
            SELECT
                COALESCE(SUM(distance_miles), 0)    AS total_miles,
                COALESCE(SUM(elapsed_time_hours), 0) AS total_hours
            FROM activities
        """).fetchone()

        pace_row = conn.execute("""
            SELECT AVG(pace) FROM activities
            WHERE type = 'Run' AND pace IS NOT NULL AND pace > 0 AND pace < 30
        """).fetchone()

        hr_row = conn.execute("""
            SELECT AVG(average_heartrate) FROM activities
            WHERE average_heartrate IS NOT NULL
        """).fetchone()

        type_rows = conn.execute("""
            SELECT type, COUNT(*) as cnt FROM activities WHERE type IS NOT NULL
            GROUP BY type ORDER BY cnt DESC
        """).fetchall()

        recent_rows = conn.execute("""
            SELECT * FROM activities ORDER BY date DESC, start_date DESC LIMIT 10
        """).fetchall()

        result = {
            "total_activities": total,
            "strava_total_count": total,
            "total_miles": round(float(totals["total_miles"] or 0), 1),
            "total_hours": round(float(totals["total_hours"] or 0), 1),
            "avg_pace": round(float(pace_row[0]), 2) if pace_row and pace_row[0] else None,
            "avg_heartrate": round(float(hr_row[0]), 1) if hr_row and hr_row[0] else None,
            "activity_types": {r["type"]: r["cnt"] for r in type_rows},
            "recent_activities": [self._row_to_summary(r) for r in recent_rows],
        }
        self._overview_cache.set("overview", result)
        return result

    def get_activity_types(self) -> List[str]:
        rows = get_conn().execute(
            "SELECT DISTINCT type FROM activities WHERE type IS NOT NULL ORDER BY type"
        ).fetchall()
        return [r[0] for r in rows]

    def get_trend_data(
        self,
        activity_type: Optional[str] = None,
        date_from:     Optional[str] = None,
        date_to:       Optional[str] = None,
    ) -> List[dict]:
        cache_key = f"trends:{activity_type}:{date_from}:{date_to}"
        cached = self._trends_cache.get(cache_key)
        if cached is not None:
            return cached

        where, params = self._build_where(
            activity_type=activity_type,
            date_from=date_from,
            date_to=date_to,
            exclude_null_date=True,
        )
        rows = get_conn().execute(
            f"SELECT * FROM activities{where} ORDER BY date ASC, start_date ASC",
            params,
        ).fetchall()

        result = [
            {
                "date": r["date"],
                "name": r["name"] or "",
                "type": r["type"] or "",
                "sport_type": r["sport_type"] or "",
                "distance_miles":    self._sf(r["distance_miles"]),
                "pace":              self._sf(r["pace"]),
                "average_speed":     self._sf(r["average_speed"]),
                "average_heartrate": self._sf(r["average_heartrate"]),
                "max_heartrate":     self._sf(r["max_heartrate"]),
                "total_elevation_gain": self._sf(r["total_elevation_gain"]),
                "moving_time_min":   self._sf(r["moving_time_min"]),
                "rolling_avg_speed":    self._sf(r["rolling_avg_speed"]),
                "rolling_avg_distance": self._sf(r["rolling_avg_distance"]),
            }
            for r in rows
        ]
        self._trends_cache.set(cache_key, result)
        return result

    def get_calendar_data(self, months: int = 12) -> List[dict]:
        cache_key = f"calendar:{months}"
        cached = self._calendar_cache.get(cache_key)
        if cached is not None:
            return cached

        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
        rows = get_conn().execute("""
            SELECT
                date,
                COUNT(*)            AS cnt,
                SUM(distance_miles) AS total_miles,
                SUM(moving_time_min) AS total_minutes,
                type
            FROM activities
            WHERE date IS NOT NULL AND date >= ?
            GROUP BY date
            ORDER BY date ASC
        """, (cutoff,)).fetchall()

        # Aggregate primary type per day (SQLite doesn't have mode() natively)
        from collections import Counter
        # Re-query to get type distribution per date
        type_rows = get_conn().execute("""
            SELECT date, type FROM activities
            WHERE date IS NOT NULL AND date >= ?
        """, (cutoff,)).fetchall()
        type_by_date: Dict[str, Counter] = {}
        for r in type_rows:
            type_by_date.setdefault(r["date"], Counter())[r["type"]] += 1

        result = []
        seen_dates = set()
        for r in rows:
            d = r["date"]
            if d in seen_dates:
                continue
            seen_dates.add(d)
            primary = type_by_date.get(d, Counter({"Run": 1})).most_common(1)[0][0]
            result.append({
                "date": d,
                "count": int(r["cnt"] or 0),
                "miles": round(float(r["total_miles"] or 0), 2),
                "minutes": round(float(r["total_minutes"] or 0), 1),
                "type": primary,
            })

        self._calendar_cache.set(cache_key, result)
        return result

    # ── Analytics: return full pandas DataFrame for PCA / similarity ───────────

    def get_activities_dataframe(
        self,
        activity_type: Optional[str] = None,
        limit: int = 10_000,
    ) -> pd.DataFrame:
        """
        Return activities as a pandas DataFrame.
        Used by pca_service and similarity_service — NOT for API responses.
        """
        where, params = self._build_where(activity_type=activity_type)
        rows = get_conn().execute(
            f"SELECT * FROM activities{where} ORDER BY date DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([dict(r) for r in rows])

    def get_analytics_cache(self) -> _TTLCache:
        """Expose analytics cache to pca_service / similarity_service."""
        return self._analytics_cache

    # ── Cache diagnostics ──────────────────────────────────────────────────────

    def get_cache_stats(self) -> dict:
        return {
            "overview":  self._overview_cache.stats(),
            "trends":    self._trends_cache.stats(),
            "calendar":  self._calendar_cache.stats(),
            "analytics": self._analytics_cache.stats(),
        }

    # ── Rolling average refresh (run after bulk import) ────────────────────────

    def recompute_rolling_averages(self):
        """
        Recompute 6-activity rolling averages for runs and persist back to DB.
        Called by SyncService after a batch import to keep derived fields fresh.
        """
        df = self.get_activities_dataframe(activity_type="Run", limit=50_000)
        if df.empty:
            return

        df = df.sort_values("date", ascending=True)

        if "average_speed" in df.columns:
            df["rolling_avg_speed"] = (
                df["average_speed"]
                .rolling(window=6, min_periods=1)
                .mean()
                .round(4)
            )
        if "distance_miles" in df.columns:
            df["rolling_avg_distance"] = (
                df["distance_miles"]
                .rolling(window=6, min_periods=1)
                .mean()
                .round(4)
            )

        conn = get_conn()
        with self._write_lock:
            for _, row in df.iterrows():
                conn.execute("""
                    UPDATE activities
                    SET rolling_avg_speed = ?, rolling_avg_distance = ?
                    WHERE id = ?
                """, (
                    self._sf(row.get("rolling_avg_speed")),
                    self._sf(row.get("rolling_avg_distance")),
                    int(row["id"]),
                ))
            conn.commit()
        logger.info("Rolling averages recomputed and persisted.")

    # ── SQL builder helpers ────────────────────────────────────────────────────

    @staticmethod
    def _build_where(
        activity_type=None, sport_type=None,
        date_from=None, date_to=None,
        min_distance=None, max_distance=None,
        exclude_null_date=False,
    ):
        clauses, params = [], []
        if activity_type:
            clauses.append("type = ?"); params.append(activity_type)
        if sport_type:
            clauses.append("sport_type = ?"); params.append(sport_type)
        if date_from:
            clauses.append("date >= ?"); params.append(date_from)
        if date_to:
            clauses.append("date <= ?"); params.append(date_to)
        if min_distance is not None:
            clauses.append("distance_miles >= ?"); params.append(min_distance)
        if max_distance is not None:
            clauses.append("distance_miles <= ?"); params.append(max_distance)
        if exclude_null_date:
            clauses.append("date IS NOT NULL")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    # ── Row → dict converters ──────────────────────────────────────────────────

    @staticmethod
    def _row_to_summary(row) -> dict:
        return {
            "id":                    int(row["id"]),
            "name":                  row["name"] or "",
            "type":                  row["type"] or "",
            "sport_type":            row["sport_type"] or "",
            "distance_miles":        DataService._sf(row["distance_miles"]),
            "moving_time_min":       DataService._sf(row["moving_time_min"]),
            "elapsed_time_min":      DataService._sf(row["elapsed_time_min"]),
            "pace":                  DataService._sf(row["pace"]),
            "average_speed":         DataService._sf(row["average_speed"]),
            "average_heartrate":     DataService._sf(row["average_heartrate"]),
            "max_heartrate":         DataService._sf(row["max_heartrate"]),
            "total_elevation_gain":  DataService._sf(row["total_elevation_gain"]),
            "date":                  row["date"] or "",
            "start_date":            row["start_date"] or "",
            "has_heartrate":         bool(row["has_heartrate"]),
            "start_latlng":          row["start_latlng"],
            "end_latlng":            row["end_latlng"],
            "trainer":               bool(row["trainer"]),
            "source":                row["source"] if "source" in row.keys() else "strava",
        }

    @staticmethod
    def _row_to_detail(row) -> dict:
        base = DataService._row_to_summary(row)
        base.update({
            "moving_time_hr":        DataService._sf(row["moving_time_hr"]),
            "elapsed_time_hours":    DataService._sf(row["elapsed_time_hours"]),
            "average_cadence":       DataService._sf(row["average_cadence"]),
            "average_watts":         DataService._sf(row["average_watts"]),
            "max_watts":             DataService._sf(row["max_watts"]),
            "elev_high":             DataService._sf(row["elev_high"]),
            "elev_low":              DataService._sf(row["elev_low"]),
            "map_polyline":          row["map_polyline"],
            "rolling_avg_speed":     DataService._sf(row["rolling_avg_speed"]),
            "rolling_avg_distance":  DataService._sf(row["rolling_avg_distance"]),
        })
        return base

    @staticmethod
    def _row_to_split(row) -> dict:
        return {
            "split_number":          DataService._sf(row["split_number"]),
            "time_seconds":          DataService._sf(row["time_seconds"]),
            "time_minutes":          row["time_minutes"] or "",
            "max_heartrate":         DataService._sf(row["max_heartrate"]),
            "avg_heartrate":         DataService._sf(row["avg_heartrate"]),
            "elevation_gain_meters": DataService._sf(row["elevation_gain_meters"]),
            "activity_id":           int(row["activity_id"]),
            "activity_name":         row["activity_name"] or "",
            "total_distance_miles":  DataService._sf(row["total_distance_miles"]),
        }

    @staticmethod
    def _row_to_summary_record(row) -> dict:
        return {
            "activity_id":                   int(row["activity_id"]),
            "activity_name":                 row["activity_name"] or "",
            "distance_miles":                DataService._sf(row["distance_miles"]),
            "fastest_time_seconds":          DataService._sf(row["fastest_time_seconds"]),
            "fastest_time_minutes":          row["fastest_time_minutes"] or "",
            "start_mile":                    DataService._sf(row["start_mile"]),
            "end_mile":                      DataService._sf(row["end_mile"]),
            "avg_heartrate_fastest":         DataService._sf(row["avg_heartrate_fastest"]),
            "elevation_gain_fastest_meters": DataService._sf(row["elevation_gain_fastest_meters"]),
        }

    # ── Upsert SQL (INSERT OR REPLACE) ─────────────────────────────────────────

    @staticmethod
    def _upsert_sql() -> str:
        return """
        INSERT INTO activities (
            id, name, type, sport_type, start_date, start_date_local, timezone,
            distance, moving_time, elapsed_time, total_elevation_gain,
            average_speed, max_speed, average_cadence, average_watts, max_watts,
            weighted_average_watts, kilojoules, device_watts,
            has_heartrate, average_heartrate, max_heartrate,
            elev_high, elev_low, trainer, commute, manual, private, flagged,
            gear_id, achievement_count, kudos_count, comment_count,
            athlete_count, photo_count, total_photo_count, pr_count, has_kudoed,
            start_latlng, end_latlng, map,
            date, distance_miles, moving_time_min, moving_time_hr,
            elapsed_time_min, elapsed_time_hours, pace,
            start_lat, start_lng, end_lat, end_lng, map_polyline
        ) VALUES (
            :id, :name, :type, :sport_type, :start_date, :start_date_local, :timezone,
            :distance, :moving_time, :elapsed_time, :total_elevation_gain,
            :average_speed, :max_speed, :average_cadence, :average_watts, :max_watts,
            :weighted_average_watts, :kilojoules, :device_watts,
            :has_heartrate, :average_heartrate, :max_heartrate,
            :elev_high, :elev_low, :trainer, :commute, :manual, :private, :flagged,
            :gear_id, :achievement_count, :kudos_count, :comment_count,
            :athlete_count, :photo_count, :total_photo_count, :pr_count, :has_kudoed,
            :start_latlng, :end_latlng, :map,
            :date, :distance_miles, :moving_time_min, :moving_time_hr,
            :elapsed_time_min, :elapsed_time_hours, :pace,
            :start_lat, :start_lng, :end_lat, :end_lng, :map_polyline
        )
        ON CONFLICT(id) DO UPDATE SET
            name               = excluded.name,
            type               = excluded.type,
            sport_type         = excluded.sport_type,
            average_heartrate  = excluded.average_heartrate,
            max_heartrate      = excluded.max_heartrate,
            total_elevation_gain = excluded.total_elevation_gain,
            map_polyline       = COALESCE(excluded.map_polyline, activities.map_polyline),
            average_cadence    = COALESCE(excluded.average_cadence, activities.average_cadence),
            average_watts      = COALESCE(excluded.average_watts,   activities.average_watts)
        """

    @staticmethod
    def _activity_to_db_params(act: dict) -> dict:
        """Convert a raw activity dict (from Strava API) to DB param dict."""
        import ast as _ast

        def _sf(v): return DataService._sf(v)
        def _sb(v): return DataService._sb(v)
        def _si(v):
            try: return int(float(v))
            except: return None

        # Derived fields
        dist_m = _sf(act.get("distance"))
        dist_miles = round(dist_m / 1609.0, 6) if dist_m else None
        mt = _si(act.get("moving_time"))
        et = _si(act.get("elapsed_time"))
        mt_min  = round(mt / 60.0, 4)   if mt else None
        mt_hr   = round(mt / 3600.0, 6) if mt else None
        et_min  = round(et / 60.0, 4)   if et else None
        et_hrs  = round(et / 3600.0, 4) if et else None
        pace    = round(mt_min / dist_miles, 4) if (mt_min and dist_miles and dist_miles > 0) else None

        sd_raw = act.get("start_date_local") or act.get("start_date") or ""
        try:
            date_str = str(sd_raw)[:10] if sd_raw else None
        except Exception:
            date_str = None

        # lat/lng
        slatlng = act.get("start_latlng")
        elatlng = act.get("end_latlng")
        def _platlng(v):
            if not v: return None, None
            try:
                if isinstance(v, str): v = _ast.literal_eval(v)
                if isinstance(v, (list, tuple)) and len(v) == 2:
                    return _sf(v[0]), _sf(v[1])
            except Exception: pass
            return None, None
        slat, slng = _platlng(slatlng)
        elat, elng = _platlng(elatlng)

        # Polyline
        map_val = act.get("map")
        polyline = None
        if map_val:
            if isinstance(map_val, dict):
                polyline = map_val.get("summary_polyline") or None
            elif isinstance(map_val, str):
                try:
                    d = _ast.literal_eval(map_val)
                    polyline = d.get("summary_polyline") if isinstance(d, dict) else None
                except Exception:
                    pass

        return {
            "id":           _si(act.get("id")),
            "name":         str(act.get("name", "") or ""),
            "type":         str(act.get("type", "") or ""),
            "sport_type":   str(act.get("sport_type", "") or ""),
            "start_date":   str(act.get("start_date", "") or ""),
            "start_date_local": str(act.get("start_date_local", "") or "") or None,
            "timezone":     str(act.get("timezone", "") or "") or None,
            "distance":     dist_m,
            "moving_time":  mt,
            "elapsed_time": et,
            "total_elevation_gain": _sf(act.get("total_elevation_gain")),
            "average_speed":   _sf(act.get("average_speed")),
            "max_speed":       _sf(act.get("max_speed")),
            "average_cadence": _sf(act.get("average_cadence")),
            "average_watts":   _sf(act.get("average_watts")),
            "max_watts":       _sf(act.get("max_watts")),
            "weighted_average_watts": _sf(act.get("weighted_average_watts")),
            "kilojoules":     _sf(act.get("kilojoules")),
            "device_watts":   _sb(act.get("device_watts")),
            "has_heartrate":  _sb(act.get("has_heartrate")),
            "average_heartrate": _sf(act.get("average_heartrate")),
            "max_heartrate":     _sf(act.get("max_heartrate")),
            "elev_high": _sf(act.get("elev_high")),
            "elev_low":  _sf(act.get("elev_low")),
            "trainer":  _sb(act.get("trainer")),
            "commute":  _sb(act.get("commute")),
            "manual":   _sb(act.get("manual")),
            "private":  _sb(act.get("private")),
            "flagged":  _sb(act.get("flagged")),
            "gear_id":  str(act.get("gear_id", "") or "") or None,
            "achievement_count":  _si(act.get("achievement_count")) or 0,
            "kudos_count":        _si(act.get("kudos_count")) or 0,
            "comment_count":      _si(act.get("comment_count")) or 0,
            "athlete_count":      _si(act.get("athlete_count")) or 0,
            "photo_count":        _si(act.get("photo_count")) or 0,
            "total_photo_count":  _si(act.get("total_photo_count")) or 0,
            "pr_count":           _si(act.get("pr_count")) or 0,
            "has_kudoed":         _sb(act.get("has_kudoed")),
            "start_latlng": str(slatlng) if slatlng else None,
            "end_latlng":   str(elatlng) if elatlng else None,
            "map":          str(map_val) if map_val else None,
            "date":         date_str,
            "distance_miles":    dist_miles,
            "moving_time_min":   mt_min,
            "moving_time_hr":    mt_hr,
            "elapsed_time_min":  et_min,
            "elapsed_time_hours": et_hrs,
            "pace":         pace,
            "start_lat":    slat,
            "start_lng":    slng,
            "end_lat":      elat,
            "end_lng":      elng,
            "map_polyline": polyline,
        }

    @staticmethod
    def _coerce(key: str, val):
        """Light type coercion for dynamic UPDATE statements."""
        bool_cols = {"trainer", "commute", "manual", "private", "flagged",
                     "has_heartrate", "device_watts", "has_kudoed"}
        float_cols = {"distance", "average_speed", "max_speed", "average_cadence",
                      "average_watts", "max_watts", "average_heartrate", "max_heartrate",
                      "total_elevation_gain", "elev_high", "elev_low"}
        if key in bool_cols:
            return DataService._sb(val)
        if key in float_cols:
            return DataService._sf(val)
        return val

    @staticmethod
    def _sf(v) -> Optional[float]:
        """Safe float — returns None for NaN/inf/invalid."""
        if v is None:
            return None
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return None
            return round(f, 4)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _sb(v) -> int:
        """Safe bool → SQLite integer (0/1)."""
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return 0
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, str):
            return 1 if v.lower() in ("true", "1", "yes", "t") else 0
        return int(bool(v))

    # ── CSV sync (legacy compat) ───────────────────────────────────────────────

    def _also_write_csv(self):
        """
        Export the activities table back to CSV so SyncService's existing
        bookkeeping (latest timestamp from CSV) continues to work.
        Called after every write. Non-fatal if it fails.
        """
        try:
            rows = get_conn().execute("SELECT * FROM activities ORDER BY date ASC").fetchall()
            if not rows:
                return
            df = pd.DataFrame([dict(r) for r in rows])
            out = DATA_DIR / "strava_activities.csv"
            tmp = out.with_suffix(".tmp")
            df.to_csv(tmp, index=False)
            tmp.replace(out)
        except Exception as e:
            logger.warning(f"CSV sync failed (non-fatal): {e}")


# ── Module-level singleton ─────────────────────────────────────────────────────

_data_service: Optional[DataService] = None
_singleton_lock = threading.Lock()


def get_data_service() -> DataService:
    global _data_service
    if _data_service is None:
        with _singleton_lock:
            if _data_service is None:
                _data_service = DataService()
    return _data_service
