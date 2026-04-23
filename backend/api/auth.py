"""
Auth API routes — Strava OAuth2 flow.
Implements Epic 1.2 endpoints.
"""
from fastapi import APIRouter, Query, HTTPException
from backend.services.strava_auth import get_strava_auth
from backend.models import schemas

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status", response_model=schemas.AuthStatusResponse)
def auth_status():
    """Check current Strava auth status and sync stats."""
    auth = get_strava_auth()
    status = auth.get_status()
    
    # Add sync status (local only to prevent hang)
    from backend.services.data_service import get_data_service
    data = get_data_service()
    
    overview = data.get_overview_stats()
    status['local_count'] = overview.get('total_activities', 0)
    # Don't fetch total count from Strava here, let the frontend use the overview endpoint
    # or let the background sync handle it.
    status['strava_total_count'] = status['local_count'] 
    
    return status


@router.get("/strava/url", response_model=schemas.AuthUrlResponse)
def get_auth_url():
    """Get the Strava OAuth authorization URL."""
    auth = get_strava_auth()
    if not auth.is_configured:
        raise HTTPException(
            status_code=500,
            detail="Strava credentials not configured. Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET."
        )
    return {"url": auth.get_auth_url()}


@router.post("/strava/callback", response_model=schemas.AuthCallbackResponse)
def auth_callback(code: str = Query(..., description="Authorization code from Strava")):
    """Exchange Strava authorization code for tokens."""
    auth = get_strava_auth()
    if not auth.is_configured:
        raise HTTPException(status_code=500, detail="Strava credentials not configured.")
    try:
        token_data = auth.exchange_code(code)
        return {
            "status": "authenticated",
            "athlete": token_data.get("athlete", {}),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")
