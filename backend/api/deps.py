"""
deps.py — FastAPI dependencies for authenticated routes.

get_current_user parses the Authorization: Bearer header and looks the token
up directly against the identity DB — the token IS the user_id, minted once
by POST /api/auth/device and never rotated.  Any route that handles user data
must declare: user_id: str = Depends(get_current_user).
"""
from fastapi import Header, HTTPException, status
from typing import Optional

from backend.services import identity_db


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> str:
    """
    Extract the bearer token from the Authorization header and verify it
    corresponds to a registered device.

    Raises 401 if the header is missing, malformed, or the token is unknown.
    Returns the user_id (== the token) on success.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    if identity_db.get_user(token) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown or revoked device token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token
