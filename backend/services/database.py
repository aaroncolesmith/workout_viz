"""
database.py — Multi-tenant SQLite/SQLCipher connection management.

Each per-user DB lives at DATA_DIR/users/<uid>/workouts.db and is opened
with a user-specific SQLCipher key supplied by the caller.  The identity DB
(users.db) is similarly encrypted.

Thread-local connection map: one connection per (thread, db_path) pair so
that concurrent FastAPI workers don't share connections across users while
still reusing connections within the same thread.

WAL mode is kept from the original design; all other analytics SQL is unchanged.
"""
import threading
import logging
from pathlib import Path
from typing import Optional

try:
    from sqlcipher3 import dbapi2 as sqlcipher
except ImportError:  # pragma: no cover — should never happen after install
    raise ImportError("sqlcipher3 is required. Install it with: pip install sqlcipher3")

logger = logging.getLogger(__name__)

# Thread-local map: db_path (str) -> sqlcipher.Connection
_local = threading.local()


# ── Connection lifecycle ──────────────────────────────────────────────────────

def get_conn(db_path: Path, key: Optional[bytes] = None) -> sqlcipher.Connection:
    """
    Return a thread-local SQLCipher connection for db_path.

    key: raw 32-byte key.  Omit only for unencrypted legacy migration work.
    First call in each thread opens the connection; subsequent calls reuse it.
    """
    path_str = str(db_path)
    conns: dict = getattr(_local, "conns", None)
    if conns is None:
        conns = {}
        _local.conns = conns

    conn = conns.get(path_str)
    if conn is None:
        conn = sqlcipher.connect(path_str, check_same_thread=False, timeout=30)
        conn.row_factory = sqlcipher.Row

        if key is not None:
            hex_key = key.hex()
            conn.execute(f"PRAGMA key = \"x'{hex_key}'\"")
            conn.execute("PRAGMA cipher_compatibility = 4")

        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-32000")
        conns[path_str] = conn

    return conn


def close_conn(db_path: Path):
    """Close and evict the thread-local connection for db_path."""
    path_str = str(db_path)
    conns: dict = getattr(_local, "conns", None) or {}
    conn = conns.pop(path_str, None)
    if conn:
        try:
            conn.close()
        except Exception:
            pass


def init_db(db_path: Path, key: Optional[bytes] = None):
    """Create schema + run migrations for a per-user workouts DB."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn(db_path, key)
    _create_schema(conn)
    logger.info(f"Workouts DB initialised at {db_path}")


# ── Schema ────────────────────────────────────────────────────────────────────

def _create_schema(conn: sqlcipher.Connection):
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
            rolling_avg_distance        REAL,
            source                      TEXT DEFAULT 'strava',
            pool_length_meters          REAL
        );

        -- ── Splits ───────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS splits (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id                 INTEGER NOT NULL,
            activity_name               TEXT,
            split_number                REAL,
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

        -- ── PR events ────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS pr_events (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id                 INTEGER NOT NULL,
            activity_name               TEXT,
            activity_type               TEXT,
            date                        TEXT,
            distance_label              TEXT,
            distance_miles              REAL,
            time_seconds                REAL,
            time_str                    TEXT,
            pace_str                    TEXT,
            previous_best_seconds       REAL,
            detected_at                 TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
        );

        -- ── Routes ───────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS routes (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            name                    TEXT NOT NULL,
            activity_type           TEXT NOT NULL DEFAULT 'Run',
            representative_polyline TEXT,
            avg_distance_miles      REAL,
            activity_count          INTEGER DEFAULT 0,
            centroid_lat            REAL,
            centroid_lng            REAL,
            best_time_seconds       REAL,
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

        -- ── Training blocks ───────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS training_blocks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            block_type  TEXT NOT NULL DEFAULT 'base',
            start_date  TEXT NOT NULL,
            end_date    TEXT NOT NULL,
            notes       TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- ── Daily health metrics (BIO-1) ─────────────────────────────────────
        CREATE TABLE IF NOT EXISTS health_metrics (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            metric              TEXT NOT NULL,
            date                TEXT NOT NULL,          -- YYYY-MM-DD (user-local day)
            value               REAL NOT NULL,
            min_value           REAL,
            max_value           REAL,
            source_id           TEXT,
            updated_at          TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (metric, date)
        );

        -- ── Swim laps ────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS swim_laps (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id         INTEGER NOT NULL,
            lap_number          INTEGER NOT NULL,
            distance_meters     REAL,
            duration_seconds    REAL NOT NULL,
            stroke_type         TEXT,
            stroke_count        INTEGER,
            avg_heartrate       REAL,
            is_rest             INTEGER DEFAULT 0,
            FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
        );

        -- ── Indexes ──────────────────────────────────────────────────────────
        CREATE INDEX IF NOT EXISTS idx_activities_type         ON activities(type);
        CREATE INDEX IF NOT EXISTS idx_activities_date         ON activities(date DESC);
        CREATE INDEX IF NOT EXISTS idx_activities_start_date   ON activities(start_date DESC);
        CREATE INDEX IF NOT EXISTS idx_splits_activity         ON splits(activity_id);
        CREATE INDEX IF NOT EXISTS idx_summaries_activity      ON summaries(activity_id);
        CREATE INDEX IF NOT EXISTS idx_sync_log_started_at     ON sync_log(started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sync_log_activity       ON sync_log(activity_id);
        CREATE INDEX IF NOT EXISTS idx_pr_events_date          ON pr_events(date DESC);
        CREATE INDEX IF NOT EXISTS idx_pr_events_activity      ON pr_events(activity_id);
        CREATE INDEX IF NOT EXISTS idx_training_blocks_dates   ON training_blocks(start_date, end_date);
        CREATE INDEX IF NOT EXISTS idx_route_activities_route  ON route_activities(route_id);
        CREATE INDEX IF NOT EXISTS idx_route_activities_activity ON route_activities(activity_id);
        CREATE INDEX IF NOT EXISTS idx_routes_type             ON routes(activity_type);
        CREATE INDEX IF NOT EXISTS idx_swim_laps_activity      ON swim_laps(activity_id);
    """)
    conn.commit()
    _migrate_schema(conn)


def _migrate_schema(conn: sqlcipher.Connection):
    """Additive migrations — safe to re-run on every open."""
    _migrate_apple_health_ids(conn)
    _dedupe_apple_health_activities(conn)
    _migrate_swim_stroke_correction(conn)
    _migrate_add_hk_source_id(conn)
    # _backfill_extended_pr_distances is triggered per-user from DataService.__init__


# ── Migrations (preserved verbatim from original) ────────────────────────────

_JS_SAFE_INT = (1 << 53) - 1


def _migrate_apple_health_ids(conn: sqlcipher.Connection):
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
            for tbl in ("splits", "summaries", "pr_events", "route_activities"):
                conn.execute(f"UPDATE {tbl} SET activity_id = ? WHERE activity_id = ?",
                             (new_id, old_id))
            migrated += 1
        except Exception as e:
            logger.warning(f"ID collision for {old_id} → {new_id}: {e}")
    conn.commit()
    if migrated:
        logger.info(f"Migrated {migrated} Apple Health activity IDs")


def _dedupe_apple_health_activities(conn: sqlcipher.Connection):
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
            f"SELECT id, map_polyline, start_date FROM activities "
            f"WHERE id IN ({','.join(['?']*len(ids))})",
            ids
        ).fetchall()

        def sort_key(r):
            return (1 if r["map_polyline"] else 0, r["start_date"] or "")

        rows_sorted = sorted(rows, key=sort_key, reverse=True)
        losers = [r["id"] for r in rows_sorted[1:]]
        for loser in losers:
            for tbl in ("splits", "summaries", "pr_events", "route_activities"):
                conn.execute(f"DELETE FROM {tbl} WHERE activity_id = ?", (loser,))
            conn.execute("DELETE FROM activities WHERE id = ?", (loser,))
            total_dropped += 1
    conn.commit()
    if total_dropped:
        logger.info(f"Deduped {total_dropped} duplicate Apple Health activities")


def _migrate_swim_stroke_correction(conn: sqlcipher.Connection):
    done = conn.execute(
        "SELECT value FROM user_settings WHERE key = 'migration_stroke_fix_v1'"
    ).fetchone()
    if done:
        return
    conn.execute("""
        UPDATE swim_laps SET stroke_type = CASE stroke_type
          WHEN 'mixed'        THEN '_m_'
          WHEN 'freestyle'    THEN '_f_'
          WHEN 'backstroke'   THEN '_b_'
          WHEN 'breaststroke' THEN '_br_'
          WHEN 'butterfly'    THEN '_bu_'
          WHEN 'kickboard'    THEN '_k_'
          ELSE stroke_type
        END
    """)
    conn.execute("""
        UPDATE swim_laps SET stroke_type = CASE stroke_type
          WHEN '_m_'  THEN NULL
          WHEN '_f_'  THEN 'mixed'
          WHEN '_b_'  THEN 'freestyle'
          WHEN '_br_' THEN 'backstroke'
          WHEN '_bu_' THEN 'breaststroke'
          WHEN '_k_'  THEN 'butterfly'
          ELSE stroke_type
        END
    """)
    conn.execute(
        "INSERT OR REPLACE INTO user_settings (key, value, updated_at) "
        "VALUES ('migration_stroke_fix_v1', 'done', CURRENT_TIMESTAMP)"
    )
    conn.commit()
    logger.info("Applied swim stroke style correction")


def _migrate_add_hk_source_id(conn: sqlcipher.Connection):
    """Add hk_source_id column for exact-match HealthKit deletions (HK-4)."""
    try:
        conn.execute("ALTER TABLE activities ADD COLUMN hk_source_id TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_hk_source ON activities(hk_source_id)")
        conn.commit()
    except Exception:
        pass  # column already exists
