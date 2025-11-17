# routers/health.py

from fastapi import APIRouter
from core.supabase_client import ping_supabase

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


# -----------------------------------------------------
# GET /health/db
# Checks Supabase connection + table queries
# No auth required
# -----------------------------------------------------
@router.get("/db", summary="Supabase / DB health check")
async def health_db():
    """
    Verifies full Supabase connectivity.
    - Checks if URL + key are configured
    - Attempts to query several tables
    - Returns row-count + error details per table
    
    Safe for external health monitors (no auth required).
    """
    try:
        status = ping_supabase()
        return {
            "service": "Supabase",
            "status": status.get("status", "unknown"),
            "details": status,
        }

    except Exception as e:
        return {
            "service": "Supabase",
            "status": "error",
            "error": str(e),
        }


# -----------------------------------------------------
# GET /health/app
# Simple API health check for Render
# -----------------------------------------------------
@router.get("/app", summary="App health check")
async def health_app():
    """
    Lightweight health check for Render or uptime monitors.
    """
    return {
        "service": "Aina API",
        "status": "ok",
    }
