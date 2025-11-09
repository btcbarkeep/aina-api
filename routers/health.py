# src/routers/health.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/db", tags=["Health"], summary="Database / Supabase health check")
async def db_health_check():
    """Database health check (Supabase placeholder)."""
    return {
        "status": "ok",
        "supabase": "not_implemented",
    }
