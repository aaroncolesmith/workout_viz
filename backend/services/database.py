"""
database.py — SQLite connection pool and schema management.

Uses a single WAL-mode SQLite database via a thread-local connection pool.
WAL mode allows concurrent reads while a write is in progress, which matters
because FastAPI runs handlers concurrently on a thread pool.

Design philosophy:
  - All raw data (activities, splits, summaries) is stored in SQLite.
  - Derived / computed columns (distance_miles, pace, rolling avgs, lat/lng)
    are stored alongside raw data so queries can filter/sort on them.
  - pandas is imported only in services that need analytics (PCA, similarity).
  - The DataService presents the same public API as before — callers don't
    know or care whether data comes from CSV or SQLite.
"""
import sqlite3
import threading
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH: Optional[Path] = None
_local = threading.local()  # thread-local connection storage


def init_db(db_path: Path):
    """Call once at startup to set the DB path and create schema."""
    global _DB_PATH
    _DB_PATH = db_path
    _create_schema()
    logger.info(f"SQLite DB initialised at {db_path}")


def get_conn() -> sqlite3.Connection:
    """
    Return a thread-local SQLite connection.
    Creates the connection on first call in each thread.
    Connections are configured for WAL mode, foreign keys, and row_factory.
    """
    if _DB_PATH is None:
        raise RuntimeError("Database not initialised — call init_db() first")

    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")  # faster than FULL, safe with WAL
        conn.execute("PRAGMA cache_size=-32000")   # 32 MB page cache
        _local.conn = conn
    return conn


def close_conn():
    """Explicitly close the thread-local connection (used in tests)."""
    conn = getattr(_local, "conn", None)
    if conn:
        conn.close()
        _local.conn = None


def _create_schema():
    """Create all tables and indexes if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        -- ── Activities ────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS activities (
            -- Strava IDs
            id                          INTEGER PRIMARY KEY,
            name                        TEXT,

            -- Raw Strava fields
            type                        TEXT,
            sport_type                  TEXT,
            start_date                  TEXT,
            start_date_local            TEXT,
            timezone                    TEXT,
            distance                    REAL,
            moving_time                 INTEGER,
            elapsed_time                INTEGER,
            total_elevation_gain        REAL,
            average_speed               REAL,
            max_speed                   REAL,
            average_cadence             REAL,
            average_watts               REAL,
            max_watts                   REAL,
            weighted_average_watts      REAL,
            kilojoules                  REAL,
            device_watts                INTEGER,
            has_heartrate               INTEGER DEFAULT 0,
            average_heartrate           REAL,
            max_heartrate               REAL,
            elev_high                   REAL,
            elev_low                    REAL,
            trainer                     INTEGER DEFAULT 0,
            commute                     INTEGER DEFAULT 0,
            manual                      INTEGER DEFAULT 0,
            private                     INTEGER DEFAULT 0,
            flagged                     INTEGER DEFAULT 0,
            gear_id                     TEXT,
            achievement_count           INTEGER DEFAULT 0,
            kudos_count                 INTEGER DEFAULT 0,
            comment_count               INTEGER DEFAULT 0,
            athlete_count               INTEGER DEFAULT 0,
            photo_count                 INTEGER DEFAULT 0,
            total_photo_count           INTEGER DEFAULT 0,
            pr_count                    INTEGER DEFAULT 0,
            has_kudoed                  INTEGER DEFAULT 0,

            -- Raw geo / map fields (stored as-is from the API)
            start_latlng                TEXT,
            end_latlng                  TEXT,
            map                         TEXT,

            -- Derived / computed fields (populated by _process_activities)
            date                        TEXT,          -- YYYY-MM-DD
            distance_miles              REAL,
            moving_time_min             REAL,
            moving_time_hr              REAL,
            elapsed_time_min            REAL,
            elapsed_time_hours          REAL,
            pace                        REAL,          -- min/mile
            start_lat                   REAL,
            start_lng                   REAL,
            end_lat                     REAL,
            end_lng                     REAL,
            map_polyline                TEXT,
            rolling_avg_speed           REAL,
            rolling_avg_distance        REAL
        );

        -- ── Splits ───────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS splits (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id                 INTEGER NOT NULL,
            activity_name               TEXT,
            split_number                REAL,          -- 0.1-mile bucket number
            time_seconds                REAL,
            time_minutes                TEXT,
            max_heartrate               REAL,
            avg_heartrate               REAL,
            avg_cadence                 REAL,
            avg_velocity                REAL,
            elevation_gain_meters       REAL,
            total_distance_miles        REAL,
            date                        TEXT,
            FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
        );

        -- ── Summaries (fastest segment data) ─────────────────────────────────
        CREATE TABLE IF NOT EXISTS summaries (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id                 INTEGER NOT NULL,
            activity_name               TEXT,
            distance_miles              REAL,
            fastest_time_seconds        REAL,
            fastest_time_minutes        TEXT,
            start_mile                  REAL,
            end_mile                    REAL,
            avg_heartrate_fastest       REAL,
            elevation_gain_fastest_meters REAL,
            FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
        );

        -- ── Sync log ─────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS sync_log (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_kind                   TEXT NOT NULL,
            status                      TEXT NOT NULL,
            deep                        INTEGER DEFAULT 0,
            activity_id                 INTEGER,
            fetched                     INTEGER DEFAULT 0,
            added                       INTEGER DEFAULT 0,
            skipped                     INTEGER DEFAULT 0,
            message                     TEXT,
            error                       TEXT,
            started_at                  TEXT,
            finished_at                 TEXT,
            created_at                  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- ── User settings (key-value store) ─────────────────────────────────
        CREATE TABLE IF NOT EXISTS user_settings (
            key                         TEXT PRIMARY KEY,
            value                       TEXT NOT NULL,
            updated_at                  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- ── PR events (personal records detected from summaries) ──────────────
        CREATE TABLE IF NOT EXISTS pr_events (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id                 INTEGER NOT NULL,
            activity_name               TEXT,
            activity_type               TEXT,
            date                        TEXT,          -- YYYY-MM-DD
            distance_label              TEXT,          -- "5K", "1 Mile", etc.
            distance_miles              REAL,
            time_seconds                REAL,
            time_str                    TEXT,
            pace_str                    TEXT,
            previous_best_seconds       REAL,          -- NULL if first effort ever
            detected_at                 TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
        );

        -- ── Routes (auto-detected clusters of same-course activities) ─────────
        CREATE TABLE IF NOT EXISTS routes (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            name                    TEXT NOT NULL,
            activity_type           TEXT NOT NULL DEFAULT 'Run',
            representative_polyline TEXT,          -- polyline of the most recent run
            avg_distance_miles      REAL,
            activity_count          INTEGER DEFAULT 0,
            centroid_lat            REAL,          -- avg start lat for geo bucketing
            centroid_lng            REAL,
            best_time_seconds       REAL,          -- best segment time (if splits exist)
            created_at              TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at              TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS route_activities (
            route_id                INTEGER NOT NULL,
            activity_id             INTEGER NOT NULL,
            similarity_score        REAL,
            PRIMARY KEY (route_id, activity_id),
            FOREIGN KEY (route_id)    REFERENCES routes(id)     ON DELETE CASCADE,
            FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
        );

        -- ── Training blocks (user-defined training phases) ───────────────────
        CREATE TABLE IF NOT EXISTS training_blocks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            block_type  TEXT NOT NULL DEFAULT 'base',  -- base | build | peak | taper | race
            start_date  TEXT NOT NULL,  -- YYYY-MM-DD
            end_date    TEXT NOT NULL,  -- YYYY-MM-DD
            notes       TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- ── Source tracking (additive; safe to run on existing DBs) ────────
        -- Handled via _migrate_schema() below; CREATE TABLE above won't add
        -- this to existing databases.

        -- ── Indexes ──────────────────────────────────────────────────────────
        CREATE INDEX IF NOT EXISTS idx_activities_type
            ON activities(type);
        CREATE INDEX IF NOT EXISTS idx_activities_date
            ON activities(date DESC);
        CREATE INDEX IF NOT EXISTS idx_activities_start_date
            ON activities(start_date DESC);
        CREATE INDEX IF NOT EXISTS idx_splits_activity
            ON splits(activity_id);
        CREATE INDEX IF NOT EXISTS idx_summaries_activity
            ON summaries(activity_id);
        CREATE INDEX IF NOT EXISTS idx_sync_log_started_at
            ON sync_log(started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sync_log_activity
            ON sync_log(activity_id);
        CREATE INDEX IF NOT EXISTS idx_pr_events_date
            ON pr_events(date DESC);
        CREATE INDEX IF NOT EXISTS idx_pr_events_activity
            ON pr_events(activity_id);
        CREATE INDEX IF NOT EXISTS idx_training_blocks_dates
            ON training_blocks(start_date, end_date);
        CREATE INDEX IF NOT EXISTS idx_route_activities_route
            ON route_activities(route_id);
        CREATE INDEX IF NOT EXISTS idx_route_activities_activity
            ON route_activities(activity_id);
        CREATE INDEX IF NOT EXISTS idx_routes_type
            ON routes(activity_type);
    """)
    conn.commit()
    _migrate_schema(conn)


def _migrate_schema(conn: sqlite3.Connection):
    """
    Additive schema migrations — safe to run on every startup.
    Each migration is idempotent (catches OperationalError for 'duplicate column').
    """
    migrations = [
        # 001 — track data source (strava | apple_health | manual)
        "ALTER TABLE activities ADD COLUMN source TEXT DEFAULT 'strava'",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists — safe to ignore

    _migrate_apple_health_ids(conn)
    _dedupe_apple_health_activities(conn)
    _backfill_extended_pr_distances(conn)


# JS Number.MAX_SAFE_INTEGER = 2^53 - 1 = 9,007,199,254,740,991
_JS_SAFE_INT = (1 << 53) - 1


def _migrate_apple_health_ids(conn: sqlite3.Connection):
    """
    Older _ah_id / _hk_id used 7-8 bytes, producing IDs that exceed JS's
    MAX_SAFE_INTEGER (2^53). When the frontend parses them via JSON they
    silently round to the nearest representable float, so subsequent API
    lookups miss the row. This migration regenerates any out-of-range
    Apple Health / HealthKit IDs using the new 6-byte algorithm.
    """
    import hashlib

    rows = conn.execute(
        "SELECT id, type, start_date FROM activities "
        "WHERE source = 'apple_health' AND ABS(id) > ?",
        (_JS_SAFE_INT,)
    ).fetchall()

    if not rows:
        return

    logger.info(f"Migrating {len(rows)} Apple Health IDs to fit in JS safe integer range")
    migrated = 0
    for row in rows:
        old_id = row["id"]
        atype = row["type"] or ""
        start_date = row["start_date"] or ""
        digest = hashlib.sha256(f"{atype}:{start_date}".encode()).digest()
        val = int.from_bytes(digest[:6], "big")
        new_id = -(val or 1)
        if new_id == old_id:
            continue
        try:
            conn.execute("UPDATE activities SET id = ? WHERE id = ?", (new_id, old_id))
            # Cascade the new ID into child tables that reference activity_id
            for tbl in ("splits", "summaries", "pr_events", "route_activities"):
                conn.execute(f"UPDATE {tbl} SET activity_id = ? WHERE activity_id = ?",
                             (new_id, old_id))
            migrated += 1
        except sqlite3.IntegrityError as e:
            logger.warning(f"ID collision for {old_id} → {new_id}: {e}")
    conn.commit()
    logger.info(f"Migrated {migrated} Apple Health activity IDs")


def _dedupe_apple_health_activities(conn: sqlite3.Connection):
    """
    Merge duplicate Apple Health activities that share the same start_time
    and type. Caused by two earlier code paths:
      - XML import used `hash(type + start_date_iso)` for IDs
      - HealthKit sync used `hash('hk:' + workout UUID)` for IDs
    Same workout, different IDs → two rows each.

    Rule: group by (type, start_date bucket = minute). For each group,
    keep the row with map_polyline populated (streams already processed);
    ties broken by latest start_date. Delete the rest — cascade drops
    their child splits/summaries/pr_events.
    """
    groups = conn.execute(
        """
        SELECT type, strftime('%Y-%m-%d %H:%M', start_date) AS bucket,
               GROUP_CONCAT(id, ',') AS ids,
               COUNT(*) AS n
          FROM activities
         WHERE source = 'apple_health'
           AND start_date IS NOT NULL
         GROUP BY type, bucket
        HAVING COUNT(*) > 1
        """
    ).fetchall()

    if not groups:
        return

    total_dropped = 0
    for g in groups:
        ids = [int(x) for x in g["ids"].split(",") if x]
        rows = conn.execute(
            f"SELECT id, map_polyline, start_date FROM activities WHERE id IN ({','.join(['?']*len(ids))})",
            ids
        ).fetchall()

        def sort_key(r):
            has_poly = 1 if r["map_polyline"] else 0
            return (has_poly, r["start_date"] or "")

        rows_sorted = sorted(rows, key=sort_key, reverse=True)
        winner = rows_sorted[0]["id"]
        losers = [r["id"] for r in rows_sorted[1:]]

        for loser in losers:
            for tbl in ("splits", "summaries", "pr_events", "route_activities"):
                conn.execute(f"DELETE FROM {tbl} WHERE activity_id = ?", (loser,))
            conn.execute("DELETE FROM activities WHERE id = ?", (loser,))
            total_dropped += 1

    conn.commit()
    if total_dropped:
        logger.info(f"Deduped {total_dropped} duplicate Apple Health activities across {len(groups)} groups")


def _backfill_extended_pr_distances(conn: sqlite3.Connection):
    """
    One-shot: recompute summaries + PR events for every activity with splits,
    so that the newly-added target distances (1/4 Mi, 1/2 Mi, 25 Mi, 50 Mi)
    show up for historical data without needing a full sync re-run.

    Idempotent via a user_settings flag. Safe to run on first startup after
    deploy; subsequent startups see the flag and no-op.
    """
    FLAG = "extended_pr_distances_backfilled"
    existing = conn.execute(
        "SELECT value FROM user_settings WHERE key = ?", (FLAG,)
    ).fetchone()
    if existing:
        return

    rows = conn.execute(
        "SELECT DISTINCT activity_id FROM splits"
    ).fetchall()
    ids = [r["activity_id"] for r in rows]
    if not ids:
        conn.execute(
            "INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, 'done')",
            (FLAG,)
        )
        conn.commit()
        return

    logger.info(f"Recomputing summaries + PRs for {len(ids)} activities (extended PR distances backfill)")

    # Import here to avoid a circular import at module load time.
    from backend.services.data_service import get_data_service
    svc = get_data_service()

    done = 0
    for aid in ids:
        try:
            svc.compute_and_save_summaries(aid)
            done += 1
        except Exception as e:
            logger.warning(f"PR backfill failed for activity {aid}: {e}")

    conn.execute(
        "INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, 'done')",
        (FLAG,)
    )
    conn.commit()
    logger.info(f"Extended PR distances backfill complete: {done} activities recomputed")
