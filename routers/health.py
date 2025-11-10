# routers/health.py
from fastapi import APIRouter
from core.supabase_client import ping_supabase

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)

@router.get("/db", summary="Database / Supabase health check")
async def db_health_check():
    """
    Checks Supabase connectivity and returns database status.
    """
    response = ping_supabase()
    return {
        "service": "Supabase",
        **response
    }

@router.get("/app", summary="App health check")
async def app_health_check():
    """
    Basic application status check.
    """
    return {"service": "Aina API", "status": "ok"}
