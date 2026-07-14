#!/usr/bin/env python3
"""
migrate_csv_to_sqlite.py — One-time migration from CSV files to SQLite.

Run from the repo root:
    python -m backend.scripts.migrate_csv_to_sqlite

The script is idempotent: rows whose 'id' already exists in SQLite are
skipped, so it's safe to re-run if a previous run was interrupted.
"""
import sys
import os
import ast
import math
import logging
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running as `python -m backend.scripts.migrate_csv_to_sqlite`
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.database import init_db, get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent.parent / "data"))
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).parent.parent / "workouts.db"))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 6)
    except (TypeError, ValueError):
        return None


def _safe_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _safe_bool(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, str):
        return 1 if v.lower() in ("true", "1", "yes", "t") else 0
    return int(bool(v))


def _parse_latlng(val):
    if not val or str(val).strip() in ("", "[]", "nan", "None"):
        return None, None
    try:
        if isinstance(val, str):
            parsed = ast.literal_eval(val)
        else:
            parsed = val
        if isinstance(parsed, (list, tuple)) and len(parsed) == 2:
            return _safe_float(parsed[0]), _safe_float(parsed[1])
    except Exception:
        pass
    return None, None


def _extract_polyline(val):
    if not val or str(val).strip() in ("", "nan", "None"):
        return None
    try:
        if isinstance(val, str):
            parsed = ast.literal_eval(val)
        else:
            parsed = val
        if isinstance(parsed, dict):
            p = parsed.get("summary_polyline", "")
            return p if p else None
    except Exception:
        pass
    return None


# ── Activities ─────────────────────────────────────────────────────────────────

def migrate_activities(df: pd.DataFrame, conn) -> int:
    """Insert activities from DataFrame into SQLite, skipping duplicates."""
    inserted = 0
    skipped = 0

    # Derived fields — same logic as DataService._process_activities
    if "distance" in df.columns:
        df["distance_miles"] = pd.to_numeric(df["distance"], errors="coerce") / 1609.0
    if "moving_time" in df.columns:
        df["moving_time_min"] = pd.to_numeric(df["moving_time"], errors="coerce") / 60.0
        df["moving_time_hr"] = pd.to_numeric(df["moving_time"], errors="coerce") / 3600.0
    if "elapsed_time" in df.columns:
        df["elapsed_time_min"] = pd.to_numeric(df["elapsed_time"], errors="coerce") / 60.0
        df["elapsed_time_hours"] = (pd.to_numeric(df["elapsed_time"], errors="coerce") / 3600.0).round(2)
    if "distance_miles" in df.columns and "moving_time_min" in df.columns:
        with np.errstate(divide="ignore", invalid="ignore"):
            pace = df["moving_time_min"] / df["distance_miles"]
            df["pace"] = pace.replace([np.inf, -np.inf], np.nan)
    if "start_date" in df.columns:
        df["date"] = pd.to_datetime(df["start_date"], errors="coerce").dt.date.astype(str)
        df["date"] = df["date"].replace("NaT", None)

    for _, row in df.iterrows():
        act_id = _safe_int(row.get("id"))
        if not act_id:
            continue

        start_lat, start_lng = _parse_latlng(row.get("start_latlng"))
        end_lat, end_lng = _parse_latlng(row.get("end_latlng"))
        polyline = _extract_polyline(row.get("map"))

        try:
            conn.execute("""
                INSERT OR IGNORE INTO activities (
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
            """, {
                "id": act_id,
                "name": str(row.get("name", "") or ""),
                "type": str(row.get("type", "") or ""),
                "sport_type": str(row.get("sport_type", "") or ""),
                "start_date": str(row.get("start_date", "") or ""),
                "start_date_local": str(row.get("start_date_local", "") or "") if row.get("start_date_local") else None,
                "timezone": str(row.get("timezone", "") or "") if row.get("timezone") else None,
                "distance": _safe_float(row.get("distance")),
                "moving_time": _safe_int(row.get("moving_time")),
                "elapsed_time": _safe_int(row.get("elapsed_time")),
                "total_elevation_gain": _safe_float(row.get("total_elevation_gain")),
                "average_speed": _safe_float(row.get("average_speed")),
                "max_speed": _safe_float(row.get("max_speed")),
                "average_cadence": _safe_float(row.get("average_cadence")),
                "average_watts": _safe_float(row.get("average_watts")),
                "max_watts": _safe_float(row.get("max_watts")),
                "weighted_average_watts": _safe_float(row.get("weighted_average_watts")),
                "kilojoules": _safe_float(row.get("kilojoules")),
                "device_watts": _safe_bool(row.get("device_watts")),
                "has_heartrate": _safe_bool(row.get("has_heartrate")),
                "average_heartrate": _safe_float(row.get("average_heartrate")),
                "max_heartrate": _safe_float(row.get("max_heartrate")),
                "elev_high": _safe_float(row.get("elev_high")),
                "elev_low": _safe_float(row.get("elev_low")),
                "trainer": _safe_bool(row.get("trainer")),
                "commute": _safe_bool(row.get("commute")),
                "manual": _safe_bool(row.get("manual")),
                "private": _safe_bool(row.get("private")),
                "flagged": _safe_bool(row.get("flagged")),
                "gear_id": str(row.get("gear_id", "")) if row.get("gear_id") else None,
                "achievement_count": _safe_int(row.get("achievement_count")) or 0,
                "kudos_count": _safe_int(row.get("kudos_count")) or 0,
                "comment_count": _safe_int(row.get("comment_count")) or 0,
                "athlete_count": _safe_int(row.get("athlete_count")) or 0,
                "photo_count": _safe_int(row.get("photo_count")) or 0,
                "total_photo_count": _safe_int(row.get("total_photo_count")) or 0,
                "pr_count": _safe_int(row.get("pr_count")) or 0,
                "has_kudoed": _safe_bool(row.get("has_kudoed")),
                "start_latlng": str(row.get("start_latlng", "")) if row.get("start_latlng") else None,
                "end_latlng": str(row.get("end_latlng", "")) if row.get("end_latlng") else None,
                "map": str(row.get("map", "")) if row.get("map") else None,
                "date": str(row.get("date", "")) if row.get("date") and str(row.get("date")) not in ("nan", "None", "NaT") else None,
                "distance_miles": _safe_float(row.get("distance_miles")),
                "moving_time_min": _safe_float(row.get("moving_time_min")),
                "moving_time_hr": _safe_float(row.get("moving_time_hr")),
                "elapsed_time_min": _safe_float(row.get("elapsed_time_min")),
                "elapsed_time_hours": _safe_float(row.get("elapsed_time_hours")),
                "pace": _safe_float(row.get("pace")),
                "start_lat": start_lat,
                "start_lng": start_lng,
                "end_lat": end_lat,
                "end_lng": end_lng,
                "map_polyline": polyline,
            })
            inserted += conn.execute("SELECT changes()").fetchone()[0]
            if conn.execute("SELECT changes()").fetchone()[0] == 0:
                skipped += 1
        except Exception as e:
            logger.warning(f"Failed to insert activity {act_id}: {e}")

    conn.commit()
    return inserted


# ── Splits ─────────────────────────────────────────────────────────────────────

def migrate_splits(df: pd.DataFrame, conn) -> int:
    inserted = 0
    for _, row in df.iterrows():
        act_id = _safe_int(row.get("activity_id") or row.get("id"))
        if not act_id:
            continue
        try:
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
                "activity_id": act_id,
                "activity_name": str(row.get("activity_name", "") or ""),
                "split_number": _safe_float(row.get("0.1_mile") or row.get("split_number")),
                "time_seconds": _safe_float(row.get("time_seconds")),
                "time_minutes": str(row.get("time_minutes", "") or ""),
                "max_heartrate": _safe_float(row.get("max_heartrate")),
                "avg_heartrate": _safe_float(row.get("avg_heartrate")),
                "avg_cadence": _safe_float(row.get("avg_cadence")),
                "avg_velocity": _safe_float(row.get("avg_velocity")),
                "elevation_gain_meters": _safe_float(row.get("elevation_gain_meters")),
                "total_distance_miles": _safe_float(row.get("total_distance_miles")),
                "date": str(row.get("date", "") or "") if row.get("date") else None,
            })
            inserted += 1
        except Exception as e:
            logger.warning(f"Failed to insert split for activity {act_id}: {e}")
    conn.commit()
    return inserted


# ── Summaries ──────────────────────────────────────────────────────────────────

def migrate_summaries(df: pd.DataFrame, conn) -> int:
    inserted = 0
    for _, row in df.iterrows():
        act_id = _safe_int(row.get("activity_id"))
        if not act_id:
            continue
        try:
            conn.execute("""
                INSERT INTO summaries (
                    activity_id, activity_name, distance_miles,
                    fastest_time_seconds, fastest_time_minutes,
                    start_mile, end_mile, avg_heartrate_fastest, elevation_gain_fastest_meters
                ) VALUES (
                    :activity_id, :activity_name, :distance_miles,
                    :fastest_time_seconds, :fastest_time_minutes,
                    :start_mile, :end_mile, :avg_heartrate_fastest, :elevation_gain_fastest_meters
                )
            """, {
                "activity_id": act_id,
                "activity_name": str(row.get("activity_name", "") or ""),
                "distance_miles": _safe_float(row.get("distance_miles")),
                "fastest_time_seconds": _safe_float(row.get("fastest_time_seconds")),
                "fastest_time_minutes": str(row.get("fastest_time_minutes", "") or ""),
                "start_mile": _safe_float(row.get("start_mile")),
                "end_mile": _safe_float(row.get("end_mile")),
                "avg_heartrate_fastest": _safe_float(row.get("avg_heartrate_fastest")),
                "elevation_gain_fastest_meters": _safe_float(row.get("elevation_gain_fastest_meters")),
            })
            inserted += 1
        except Exception as e:
            logger.warning(f"Failed to insert summary for activity {act_id}: {e}")
    conn.commit()
    return inserted


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    logger.info(f"Migrating CSV data from {DATA_DIR} → {DB_PATH}")

    init_db(DB_PATH)
    conn = get_conn()

    # Activities
    acts_path = DATA_DIR / "strava_activities.csv"
    if acts_path.exists():
        logger.info(f"Reading {acts_path} …")
        df = pd.read_csv(acts_path, low_memory=False)
        logger.info(f"  {len(df)} rows. Migrating…")
        n = migrate_activities(df, conn)
        total = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        logger.info(f"  ✓ Inserted {n} new rows. DB total: {total}")
    else:
        logger.warning(f"Activities CSV not found at {acts_path}")

    # Splits — clear & reload to avoid duplicates (autoincrement IDs)
    splits_path = DATA_DIR / "strava_splits.csv"
    if splits_path.exists():
        logger.info(f"Reading {splits_path} …")
        df = pd.read_csv(splits_path, low_memory=False)
        existing = conn.execute("SELECT COUNT(*) FROM splits").fetchone()[0]
        if existing == 0:
            logger.info(f"  {len(df)} rows. Migrating…")
            n = migrate_splits(df, conn)
            logger.info(f"  ✓ Inserted {n} splits")
        else:
            logger.info(f"  Splits table already has {existing} rows — skipping (re-run with --force to overwrite)")
    else:
        logger.warning(f"Splits CSV not found at {splits_path}")

    # Summaries
    summary_path = DATA_DIR / "strava_summary.csv"
    if summary_path.exists():
        logger.info(f"Reading {summary_path} …")
        df = pd.read_csv(summary_path, low_memory=False)
        existing = conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
        if existing == 0:
            logger.info(f"  {len(df)} rows. Migrating…")
            n = migrate_summaries(df, conn)
            logger.info(f"  ✓ Inserted {n} summaries")
        else:
            logger.info(f"  Summaries table already has {existing} rows — skipping")
    else:
        logger.warning(f"Summary CSV not found at {summary_path}")

    # Final counts
    logger.info("Migration complete.")
    logger.info(f"  Activities : {conn.execute('SELECT COUNT(*) FROM activities').fetchone()[0]}")
    logger.info(f"  Splits     : {conn.execute('SELECT COUNT(*) FROM splits').fetchone()[0]}")
    logger.info(f"  Summaries  : {conn.execute('SELECT COUNT(*) FROM summaries').fetchone()[0]}")


if __name__ == "__main__":
    main()
