"""
identity_db.py — Central identity registry.

Stores devices (one opaque token per install, doubling as user_id) and their
wrapped per-user DEKs.  Single SQLCipher file at DATA_DIR/users.db, keyed
from the master via key_provider.identity_db_key() — no per-row DEK needed
here.

Connections come from database.get_conn, which caches per (thread, path).
"""
import os
import logging
from pathlib import Path

from backend.services.database import get_conn, init_db as _init_workouts_db
from backend.services.key_provider import identity_db_key, generate_dek, wrap_dek, unwrap_dek

logger = logging.getLogger(__name__)

_identity_db_path: Path | None = None


def default_data_dir() -> Path:
    """
    Single source of truth for the data directory.  Must match everywhere
    (identity DB, per-user DBs) or users get provisioned in one tree and
    served from another.
    """
    return Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data"))


def _get_path() -> Path:
    if _identity_db_path is None:
        raise RuntimeError("Identity DB not initialised — call init_identity_db() first")
    return _identity_db_path


def get_identity_conn():
    """Return the thread-local SQLCipher connection to users.db
    (get_conn caches per (thread, path))."""
    return get_conn(_get_path(), key=identity_db_key())


def init_identity_db(data_dir: Path | None = None):
    """Create users.db and its schema.  Call once at startup."""
    global _identity_db_path

    if data_dir is None:
        data_dir = default_data_dir()

    _identity_db_path = data_dir / "users.db"
    _identity_db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_identity_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- wrapped per-user DEKs (AES-GCM, key = master)
        CREATE TABLE IF NOT EXISTS user_deks (
            user_id     TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            wrapped_dek BLOB NOT NULL
        );
    """)
    conn.commit()
    logger.info(f"Identity DB initialised at {_identity_db_path}")


# ── Device registration ─────────────────────────────────────────────────────

def register_device(data_dir: Path | None = None) -> str:
    """
    Provision a brand-new device identity: a random opaque token that doubles
    as the user_id, a wrapped DEK, and an empty per-user workouts DB.

    Returns the token — the caller (POST /api/auth/device) hands it straight
    back to the client, which stores it and uses it as the Bearer credential
    forever.
    """
    import secrets
    from datetime import datetime, timezone

    if data_dir is None:
        data_dir = default_data_dir()

    conn = get_identity_conn()
    now = datetime.now(timezone.utc).isoformat()
    user_id = secrets.token_hex(32)

    conn.execute(
        "INSERT INTO users (id, created_at) VALUES (?, ?)", (user_id, now)
    )

    dek = generate_dek()
    wrapped = wrap_dek(dek)
    conn.execute(
        "INSERT INTO user_deks (user_id, wrapped_dek) VALUES (?, ?)",
        (user_id, wrapped),
    )
    conn.commit()

    db_path = _user_db_path(user_id, data_dir)
    _init_workouts_db(db_path, key=dek)
    logger.info(f"Provisioned new device {user_id} with encrypted workouts DB")

    return user_id


def get_user_dek(user_id: str) -> bytes:
    """Unwrap and return the raw 32-byte DEK for user_id."""
    conn = get_identity_conn()
    row = conn.execute(
        "SELECT wrapped_dek FROM user_deks WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not row:
        raise KeyError(f"No DEK found for user {user_id}")
    return unwrap_dek(bytes(row["wrapped_dek"]))


def get_user(user_id: str) -> dict | None:
    conn = get_identity_conn()
    row = conn.execute(
        "SELECT id, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return dict(row) if row else None


def purge_user(user_id: str, data_dir: Path | None = None) -> None:
    """
    Permanently delete all data for a user — the per-user workouts DB and all
    identity DB rows.  CASCADE constraint handles user_deks.
    Irreversible.  COMP-1 / App Store data-deletion requirement.
    """
    import shutil

    if data_dir is None:
        data_dir = default_data_dir()

    # Remove the per-user workouts directory (DB + any CSV exports)
    user_dir = data_dir / "users" / user_id
    if user_dir.exists():
        shutil.rmtree(user_dir, ignore_errors=True)
        logger.info(f"Deleted data directory for user {user_id}")

    # Remove from identity DB (CASCADE drops user_deks)
    conn = get_identity_conn()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    logger.info(f"Purged identity records for user {user_id}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _user_db_path(user_id: str, data_dir: Path) -> Path:
    return data_dir / "users" / user_id / "workouts.db"


def get_user_db_path(user_id: str, data_dir: Path | None = None) -> Path:
    if data_dir is None:
        data_dir = default_data_dir()
    return _user_db_path(user_id, data_dir)
