# src/routers/health.py
from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/db", summary="Database / Supabase health check")
async def db_health_check():
    """
    Placeholder endpoint – later we will actually ping Supabase.
    """
    return {
        "status": "ok",
        "supabase": "not_implemented",
    }
