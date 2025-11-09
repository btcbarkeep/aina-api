# src/routers/__init__.py
from fastapi import APIRouter

from . import auth, buildings, events, uploads, documents, health

api_router = APIRouter()

# Group routers with their own prefixes
api_router.include_router(auth.router)
api_router.include_router(buildings.router, prefix="/buildings", tags=["buildings"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(health.router)

__all__ = ["api_router"]
# keep this file present (can be empty)

