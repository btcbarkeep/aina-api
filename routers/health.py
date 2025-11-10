# routers/health.py
from fastapi import APIRouter
from core.supabase_client import ping_supabase

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)

"""
Health endpoints provide system and database status checks for uptime monitoring,
including /db (database connectivity) and /app (application status).
"""


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
