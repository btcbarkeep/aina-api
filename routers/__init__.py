# routers/__init__.py
from fastapi import APIRouter
from . import auth, buildings, events, uploads, sync, documents, health

api_router = APIRouter()

# Each router already has its own prefix and tags defined
api_router.include_router(auth.router)
api_router.include_router(buildings.router)
api_router.include_router(events.router)
api_router.include_router(uploads.router)
api_router.include_router(sync.router)
api_router.include_router(documents.router)
api_router.include_router(health.router)

__all__ = ["api_router"]
