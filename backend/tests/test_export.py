"""
PLT-4 — the COMP-2 export must contain every user-data table, most
importantly daily biometrics.
"""
import json
import sqlite3
import zipfile

from backend.api.auth import _EXPORT_TABLES, build_export_zip
from backend.services import health_metrics_service as hm


def test_export_covers_every_user_table(seeded_backend):
    conn = seeded_backend["service"]._conn()

    # Every table in the per-user schema (minus sqlite internals) must be
    # exported — a new migration that forgets the export list fails here.
    schema_tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    assert schema_tables == set(_EXPORT_TABLES), (
        "Export table list is out of sync with the schema — "
        f"missing: {schema_tables - set(_EXPORT_TABLES)}, "
        f"stale: {set(_EXPORT_TABLES) - schema_tables}"
    )


def test_export_zip_contains_health_metrics(seeded_backend):
    conn = seeded_backend["service"]._conn()
    hm.upsert_metrics(conn, [
        {"metric": "resting_heartrate", "date": "2026-07-10", "value": 52.0},
        {"metric": "sleep_asleep", "date": "2026-07-10", "value": 7.4},
    ])

    buf = build_export_zip(conn, seeded_backend["user_id"])
    with zipfile.ZipFile(buf) as zf:
        names = set(zf.namelist())
        assert {f"{t}.json" for t in _EXPORT_TABLES} <= names
        assert "manifest.json" in names

        metrics = json.loads(zf.read("health_metrics.json"))
        assert len(metrics) == 2
        assert {m["metric"] for m in metrics} == {"resting_heartrate", "sleep_asleep"}

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["row_counts"]["health_metrics"] == 2
        assert manifest["row_counts"]["activities"] == 4
