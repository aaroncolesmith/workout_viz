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
