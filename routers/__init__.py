# routers/__init__.py
from fastapi import APIRouter
from . import auth, buildings, events, uploads, sync, documents, health, admin, auth_password, signup

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(buildings.router)
api_router.include_router(events.router)
api_router.include_router(uploads.router)
api_router.include_router(sync.router)
api_router.include_router(documents.router)
api_router.include_router(health.router)
api_router.include_router(admin.router)
api_router.include_router(auth_password.router)
api_router.include_router(signup.router)


__all__ = ["api_router"]
