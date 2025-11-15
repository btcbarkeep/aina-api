# routers/__init__.py

from fastapi import APIRouter

# Import new Supabase-only routers + auth/admin/etc
from .auth import router as auth_router
from .signup import router as signup_router
from .admin import router as admin_router
from .user_access import router as user_access_router

from .buildings_supabase import router as buildings_router
from .events_supabase import router as events_router
from .documents_supabase import router as documents_router

from .admin_daily import router as admin_daily_router
from .uploads import router as uploads_router


# Master router (deprecated but left for compatibility)
api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(signup_router)
api_router.include_router(admin_router)
api_router.include_router(user_access_router)

# Supabase-only routers
api_router.include_router(buildings_router)
api_router.include_router(events_router)
api_router.include_router(documents_router)

# Uploads (still needed)
api_router.include_router(uploads_router)

# Daily admin summary
api_router.include_router(admin_daily_router)

__all__ = ["api_router"]
