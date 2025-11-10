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

import os

@router.get("/env", summary="Environment variable check (masked)")
async def env_check():
    """Check what environment variables are actually loaded at runtime."""
    return {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_API_KEY": "SET" if os.getenv("SUPABASE_API_KEY") else "MISSING",
        "All Keys": list(os.environ.keys())[:20],  # show first 20 keys for context
    }

