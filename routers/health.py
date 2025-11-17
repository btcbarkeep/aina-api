from fastapi import APIRouter, HTTPException
from core.supabase_client import ping_supabase

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)

# -----------------------------------------------------
# DB HEALTH CHECK
# -----------------------------------------------------
@router.get("/db", summary="Database / Supabase health check")
async def db_health_check():
    """
    Verifies connectivity to Supabase.
    This endpoint intentionally requires NO AUTH,
    so Render or external monitors can check health.
    """
    try:
        response = ping_supabase()
    except Exception as e:
        return {
            "service": "Supabase",
            "status": "error",
            "detail": str(e),
        }

    return {
        "service": "Supabase",
        **response
    }

# -----------------------------------------------------
# APP HEALTH CHECK
# -----------------------------------------------------
@router.get("/app", summary="App health check")
async def app_health_check():
    """
    Basic application health check.
    Useful for Render's health checks or uptime monitors.
    """
    return {
        "service": "Aina API",
        "status": "ok"
    }
