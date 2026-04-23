"""
Strava OAuth2 service — handles authorization flow and token management.
Ported from notebook's get_strava_auth() / load_strava_data() / update_strava_data().
"""
import os
import json
import time
import requests
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data")) / ".strava_token.json"

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


class StravaAuthService:
    """Manages Strava OAuth2 tokens and API authentication."""

    def __init__(self):
        self.client_id = os.getenv("STRAVA_CLIENT_ID", "")
        self.client_secret = os.getenv("STRAVA_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:5173/auth/callback")
        self._token_data: Optional[dict] = None
        self._load_token()

    def _load_token(self):
        """Load saved token from disk."""
        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, "r") as f:
                    self._token_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._token_data = None

    def _save_token(self, token_data: dict):
        """Persist token to disk."""
        self._token_data = token_data
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            json.dump(token_data, f, indent=2)

    @property
    def is_configured(self) -> bool:
        """Check if Strava credentials are set."""
        return bool(self.client_id and self.client_secret)

    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        return self._token_data is not None and 'access_token' in self._token_data

    def get_auth_url(self) -> str:
        """Generate the Strava OAuth authorization URL."""
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'approval_prompt': 'auto',
            'scope': 'activity:read_all',
        }
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{STRAVA_AUTH_URL}?{param_str}"

    def exchange_code(self, code: str) -> dict:
        """
        Exchange authorization code for access + refresh tokens.
        Ported from notebook's get_strava_auth().
        """
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
        }
        response = requests.post(STRAVA_TOKEN_URL, data=payload, timeout=10)
        response.raise_for_status()
        token_data = response.json()
        self._save_token(token_data)
        return token_data

    def refresh_token(self) -> dict:
        """Refresh the access token using the saved refresh_token."""
        if not self._token_data or 'refresh_token' not in self._token_data:
            raise ValueError("No refresh token available. Please re-authenticate.")

        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self._token_data['refresh_token'],
            'grant_type': 'refresh_token',
        }
        response = requests.post(STRAVA_TOKEN_URL, data=payload, timeout=10)
        response.raise_for_status()
        token_data = response.json()
        self._save_token(token_data)
        return token_data

    def get_access_token(self) -> str:
        """Get a valid access token, refreshing if expired."""
        if not self._token_data:
            raise ValueError("Not authenticated. Please connect your Strava account.")

        # Check if token is expired
        expires_at = self._token_data.get('expires_at', 0)
        if time.time() >= expires_at:
            self.refresh_token()

        return self._token_data['access_token']

    def get_headers(self) -> dict:
        """Get Authorization headers for Strava API requests."""
        return {'Authorization': f'Bearer {self.get_access_token()}'}

    def get_status(self) -> dict:
        """Return current auth status."""
        return {
            'configured': self.is_configured,
            'authenticated': self.is_authenticated,
            'auth_url': self.get_auth_url() if self.is_configured else None,
        }


# Singleton
_strava_auth: Optional[StravaAuthService] = None


def get_strava_auth() -> StravaAuthService:
    global _strava_auth
    if _strava_auth is None:
        _strava_auth = StravaAuthService()
    return _strava_auth
