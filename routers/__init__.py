# routers/__init__.py
from fastapi import APIRouter
from . import auth, buildings, events, uploads, documents, health

api_router = APIRouter()

# Each router already defines its own prefix (e.g., "/buildings")
# So we include them without adding a second prefix here
api_router.include_router(auth.router, tags=["Auth"])
api_router.include_router(buildings.router, tags=["Buildings"])
api_router.include_router(events.router, tags=["Events"])
api_router.include_router(uploads.router, tags=["Uploads"])
api_router.include_router(documents.router, tags=["Documents"])
api_router.include_router(health.router, tags=["Health"])

__all__ = ["api_router"]
