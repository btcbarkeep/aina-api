# main.py
import os
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.scheduler import start_scheduler


# Local imports
from core.config import settings
from core.logging_config import logger
from database import create_db_and_tables
from routers import api_router
from routers import user_access


# Ensure local imports always resolve correctly
sys.path.append(os.path.dirname(__file__))


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.3.0",
        description="Aina Protocol API – Real Estate Data & AOAO Management on-chain",
    )

    # -------------------------------------------------
    # CORS
    # -------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS] or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -------------------------------------------------
    # Startup
    # -------------------------------------------------
    @app.on_event("startup")
    async def on_startup():
        logger.info("🚀 Starting Aina Protocol API")
        create_db_and_tables()

        # Log all /api/v1 routes for quick Render visibility
        print("\n📍 Registered /api/v1 Routes:\n")
        for route in app.routes:
            if route.path.startswith("/api/v1"):
                methods = ",".join(route.methods or [])
                print(f"➡️  {methods:10s} {route.path}")
        print("\n✅ Route log complete.\n")

        start_scheduler()


    # -------------------------------------------------
    # Centralized error logging
    # -------------------------------------------------
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code in (401, 403, 500):
            logger.warning(
                "HTTP %s at %s - detail=%s",
                exc.status_code,
                request.url,
                exc.detail,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled server error at %s", request.url, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

     # -------------------------------------------------
    # Versioned API: everything under /api/v1
    # -------------------------------------------------
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    app.include_router(user_access.router, prefix="/api/v1/user-access")


    # -------------------------------------------------
    # Health routes (non-versioned)
    # -------------------------------------------------
    from routers import health
    app.include_router(health.router)

    # -------------------------------------------------
    # Root endpoint (uptime / info)
    # -------------------------------------------------
    @app.get("/", tags=["Health"], summary="API Uptime & Version Check")
    async def root():
        """Simple root route for uptime monitoring (e.g., Render health check)."""
        return {
            "status": "ok",
            "message": "Aina Protocol API",
            "version": app.version,
        }

    return app



app = create_app()
