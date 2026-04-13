"""
Racing Dashboard — FastAPI Backend
Main application entry point.
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.races import router as races_router, _refresh_meetings
from api.bets import router as bets_router
from services.file_watcher import FileWatcher
import config
import logging

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Racing Dashboard API",
    description="Real-time horse racing analysis dashboard API",
    version="1.1.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(races_router, prefix="/api")
app.include_router(bets_router, prefix="/api")

# File watcher — auto-detect new analysis files
file_watcher = FileWatcher(on_change_callback=_refresh_meetings)


@app.on_event("startup")
def startup():
    file_watcher.start()


@app.on_event("shutdown")
def shutdown():
    file_watcher.stop()


@app.get("/api/status")
def get_status():
    """Return system status including file watcher state."""
    from api.races import _get_meetings
    meetings = _get_meetings()
    return {
        "last_updated": file_watcher.last_updated,
        "meeting_count": len(meetings),
        "watcher": file_watcher.get_status(),
    }


# ── Serve production frontend build ──
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if DIST_DIR.exists():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve index.html for all non-API routes (SPA catch-all)."""
        # Try to serve the exact file first
        file_path = DIST_DIR / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # Fall back to index.html for SPA routing
        return FileResponse(str(DIST_DIR / "index.html"))
else:
    @app.get("/")
    def health():
        return {"status": "ok", "version": "1.1.0", "note": "No frontend build found. Run npm run build in frontend/"}
