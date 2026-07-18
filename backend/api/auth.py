"""
auth.py — Device identity endpoints.

POST   /api/auth/device           — Register a new device, returns a permanent
                                     Bearer token (== user_id).  No accounts,
                                     no OAuth, no expiry.
DELETE /api/auth/account          — Permanently delete this device's data (COMP-1)
GET    /api/auth/account/export   — Export this device's data as a ZIP (COMP-2)

Strava routes are kept dormant behind STRAVA_AUTH_ENABLED=true; they are not
reachable in production until that env var is set.
"""
import io
import json
import os
import logging
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.models import schemas
from backend.services.identity_db import register_device
from backend.api.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

_STRAVA_ENABLED = os.environ.get("STRAVA_AUTH_ENABLED", "").lower() == "true"


# ── Device registration ──────────────────────────────────────────────────────

@router.post("/device", response_model=schemas.DeviceRegisterResponse)
def register():
    """Provision a brand-new device identity and return its permanent token."""
    device_token = register_device()
    return {"device_token": device_token}


# ── Account deletion (COMP-1) ────────────────────────────────────────────────

@router.delete("/account", status_code=204)
def delete_account(user_id: str = Depends(get_current_user)):
    """
    Permanently delete this device's data.  Required by App Store guidelines
    (section 5.1.1 — data deletion).  The bearer token is dead after this
    call — the client must forget it locally.
    """
    from backend.services.identity_db import purge_user
    purge_user(user_id)


# ── Data export (COMP-2) ──────────────────────────────────────────────────────

# Every user-data table in the per-device DB.  If a migration adds a table,
# it belongs here — the export IS the data-portability promise, and daily
# biometrics (health_metrics) are the most personal rows in the DB.
_EXPORT_TABLES = {
    "activities":       "SELECT * FROM activities",
    "splits":           "SELECT * FROM splits",
    "summaries":        "SELECT * FROM summaries",
    "pr_events":        "SELECT * FROM pr_events",
    "swim_laps":        "SELECT * FROM swim_laps",
    "health_metrics":   "SELECT * FROM health_metrics",
    "routes":           "SELECT * FROM routes",
    "route_activities": "SELECT * FROM route_activities",
    "training_blocks":  "SELECT * FROM training_blocks",
    "user_settings":    "SELECT * FROM user_settings",
    "sync_log":         "SELECT * FROM sync_log",
}


def build_export_zip(conn, user_id: str) -> io.BytesIO:
    """Build the COMP-2 export archive; split out so tests can open the ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "export_date": datetime.now(timezone.utc).isoformat(),
            "user_id":     user_id,
            "app":         "Volken",
            "row_counts":  {},
        }
        for name, query in _EXPORT_TABLES.items():
            rows = [dict(r) for r in conn.execute(query).fetchall()]
            manifest["row_counts"][name] = len(rows)
            zf.writestr(f"{name}.json", json.dumps(rows, indent=2, default=str))

        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    buf.seek(0)
    return buf


@router.get("/account/export")
def export_account(user_id: str = Depends(get_current_user)):
    """
    Export all of this device's data as a ZIP archive containing JSON tables.
    Recommended by App Store guidelines for data portability.
    """
    from backend.services.data_service import get_data_service

    svc = get_data_service(user_id)
    buf = build_export_zip(svc._conn(), user_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"volken_export_{stamp}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Strava (dormant) ──────────────────────────────────────────────────────────

if _STRAVA_ENABLED:
    from fastapi import Query
    from backend.services.strava_auth import get_strava_auth

    @router.get("/strava/url")
    def get_strava_auth_url():
        auth = get_strava_auth()
        if not auth.is_configured:
            raise HTTPException(status_code=500, detail="Strava not configured")
        return {"url": auth.get_auth_url()}

    @router.post("/strava/callback")
    def strava_callback(code: str = Query(...)):
        auth = get_strava_auth()
        try:
            token_data = auth.exchange_code(code)
            return {"status": "authenticated", "athlete": token_data.get("athlete", {})}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
