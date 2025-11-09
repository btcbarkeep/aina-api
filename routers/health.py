# routers/health.py
from fastapi import APIRouter

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
    Placeholder endpoint – later we will actually ping Supabase.
    """
    return {
        "status": "ok",
        "supabase": "not_implemented",
    }
