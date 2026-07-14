"""
Workout Viz — FastAPI Application
Main entry point for the backend API server.
"""
import os
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from backend.models import schemas

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Workout Viz API",
    description="Personal fitness analytics — Strava activity data, similarity engine, and trend analysis.",
    version="0.2.0",
)

# CORS for local dev (Vite runs on 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve built React app in production (when frontend/dist exists)
_DIST = Path(__file__).parent.parent / "frontend" / "dist"

@app.middleware("http")
async def log_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        import traceback
        logger.error(f"UNHANDLED ERROR: {e}\n{traceback.format_exc()}")
        raise e


# ── Startup: init identity DB ─────────────────────────────────────────────────
def _init_services():
    """
    Initialise the central identity DB (users.db).
    Per-user workouts DBs are created lazily at first login.
    Runs in a daemon thread so the health endpoint responds immediately.
    """
    try:
        from backend.services.identity_db import init_identity_db
        init_identity_db()
        logger.info("Identity DB initialised — ready for logins")
    except Exception:
        logger.exception("Background startup init failed")


@app.on_event("startup")
def on_startup():
    import threading
    threading.Thread(target=_init_services, name="startup-init", daemon=True).start()


# ── Route modules ──────────────────────────────────────────────────────────────
from backend.api.activities import router as activities_router
from backend.api.auth import router as auth_router
from backend.api.import_routes import router as import_router
from backend.api.health import router as health_router

app.include_router(activities_router)
app.include_router(auth_router)
app.include_router(import_router)
app.include_router(health_router)


# ── Utility endpoints ──────────────────────────────────────────────────────────
@app.get("/api", response_model=schemas.RootResponse)
@app.get("/api/", response_model=schemas.RootResponse)
def root():
    return {"app": "Workout Viz API", "version": "0.2.0", "docs": "/docs"}


@app.get("/health", response_model=schemas.HealthResponse)
def health():
    return {"status": "ok"}



# ── Static file serving (production) ──────────────────────────────────────────
# Registered last so all /api/* routes take priority.
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # Return index.html for all client-side routes (React Router handles them)
        index = _DIST / "index.html"
        if full_path and (_DIST / full_path).is_file():
            return FileResponse(str(_DIST / full_path))
        # Never cache index.html — hashed assets handle their own caching
        return FileResponse(
            str(index),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
