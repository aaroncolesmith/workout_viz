"""
rotate_master_key.py — COMP-4: Re-wrap all per-user DEKs under a new master key.

This script performs a master key rotation:
  1. Opens the identity DB (users.db) — with the OLD derived key, falling back
     to the NEW derived key so an interrupted run can be resumed.
  2. Unwraps each per-user DEK with the old master (falling back to the new
     master for rows already rotated by a previous interrupted run).
  3. Re-wraps every DEK with the new master and commits.
  4. Re-keys users.db itself to the new derived key (skipped when the DB was
     already opened with the new key).

The per-user workouts.db files are NOT touched — their DEKs are unchanged, only
the envelope (wrapped DEK in users.db) is rotated.

The run is idempotent: if it crashes at any point, re-running it with the same
OLD_MASTER_KEY / NEW_MASTER_KEY completes the rotation.  All crypto goes
through key_provider so the envelope format cannot drift from the server's.

Usage:
    OLD_MASTER_KEY=<hex>  NEW_MASTER_KEY=<hex>  DATA_DIR=/data  \\
        python -m backend.scripts.rotate_master_key

Both keys must be 64 hex characters (32 bytes).  Scale the app to zero
replicas while the script runs to avoid split-brain reads.  Afterwards set
DB_ENCRYPTION_MASTER_KEY to the new key and restart.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _parse_key(env_var: str) -> bytes:
    raw = os.environ.get(env_var, "")
    if not raw:
        print(f"ERROR: {env_var} is not set", file=sys.stderr)
        sys.exit(1)
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        print(f"ERROR: {env_var} is not valid hex", file=sys.stderr)
        sys.exit(1)
    if len(key) != 32:
        print(f"ERROR: {env_var} must decode to 32 bytes, got {len(key)}", file=sys.stderr)
        sys.exit(1)
    return key


def _open_identity_db(sc, identity_db: Path, id_key: bytes):
    """Open users.db with the given derived key; return conn or None."""
    conn = sc.connect(str(identity_db), check_same_thread=False)
    conn.execute(f"PRAGMA key = \"x'{id_key.hex()}'\"")
    conn.execute("PRAGMA cipher_compatibility = 4")
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return conn
    except Exception:
        conn.close()
        return None


def main() -> int:
    load_dotenv()

    old_key = _parse_key("OLD_MASTER_KEY")
    new_key = _parse_key("NEW_MASTER_KEY")

    if old_key == new_key:
        print("OLD_MASTER_KEY and NEW_MASTER_KEY are identical — nothing to do.")
        return 0

    from backend.services.identity_db import default_data_dir
    from backend.services.key_provider import identity_db_key, unwrap_dek, wrap_dek

    data_dir = Path(os.environ["DATA_DIR"]) if os.environ.get("DATA_DIR") else default_data_dir()
    identity_db = data_dir / "users.db"

    if not identity_db.exists():
        print(f"ERROR: Identity DB not found at {identity_db}", file=sys.stderr)
        return 1

    try:
        from sqlcipher3 import dbapi2 as sc
    except ImportError:
        print("ERROR: sqlcipher3 not installed", file=sys.stderr)
        return 1

    old_id_key = identity_db_key(master=old_key)
    new_id_key = identity_db_key(master=new_key)

    # ── 1. Open identity DB: old key first, new key if a prior run already
    #        re-keyed it (resume support) ──────────────────────────────────────
    conn = _open_identity_db(sc, identity_db, old_id_key)
    already_rekeyed = False
    if conn is None:
        conn = _open_identity_db(sc, identity_db, new_id_key)
        already_rekeyed = conn is not None
    if conn is None:
        print("ERROR: users.db opens with neither the old nor the new key.", file=sys.stderr)
        return 1
    if already_rekeyed:
        print("users.db already re-keyed by a previous run — resuming DEK rotation.")

    rows = conn.execute("SELECT user_id, wrapped_dek FROM user_deks").fetchall()
    print(f"Found {len(rows)} user DEK(s) to rotate.")

    # ── 2. Unwrap (old master, falling back to new for already-rotated rows)
    #        and re-wrap with the new master ─────────────────────────────────
    updates: list[tuple[bytes, str]] = []
    for user_id, wrapped_blob in rows:
        wrapped = bytes(wrapped_blob)
        try:
            raw_dek = unwrap_dek(wrapped, master=old_key)
        except Exception:
            try:
                unwrap_dek(wrapped, master=new_key)
                continue  # already rotated by a previous interrupted run
            except Exception as exc:
                print(f"ERROR: DEK for user {user_id} unwraps with neither key: {exc}",
                      file=sys.stderr)
                conn.close()
                return 1
        updates.append((wrap_dek(raw_dek, master=new_key), user_id))

    # ── 3. Write new wrapped DEKs ────────────────────────────────────────────
    for new_wrapped, user_id in updates:
        conn.execute(
            "UPDATE user_deks SET wrapped_dek = ? WHERE user_id = ?",
            (new_wrapped, user_id),
        )
    conn.commit()
    print(f"Re-wrapped {len(updates)} DEK(s) ({len(rows) - len(updates)} already rotated).")

    # ── 4. Re-key the identity DB itself ─────────────────────────────────────
    if not already_rekeyed:
        conn.execute(f"PRAGMA rekey = \"x'{new_id_key.hex()}'\"")
        print("Identity DB re-keyed successfully.")
    conn.close()

    print("\nRotation complete.")
    print("Next steps:")
    print("  1. Set DB_ENCRYPTION_MASTER_KEY to the NEW key in production (fly secrets set ...).")
    print("  2. Restart app replicas.")
    print("  3. Verify a login works before deleting the old key from your password manager.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
