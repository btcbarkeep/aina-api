# main.py
import os
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Ensure relative imports work
sys.path.append(os.path.dirname(__file__))

# Core / DB
from core.config import settings
from core.logging_config import logger
from database import create_db_and_tables

# Routers (Supabase-only + Auth)
from routers.buildings_supabase import router as buildings_router
from routers.events_supabase import router as events_router
from routers.documents_supabase import router as documents_router
from routers.admin import router as admin_router
from routers.user_access import router as user_access_router
from routers.auth import router as auth_router
from routers.signup import router as signup_router
from routers.admin_daily import router as admin_daily_router   # NEW DAILY REPORT


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.4.0",
        description="Aina Protocol API — Supabase-powered Real Estate Reporting",
    )

    # -------------------------------------------------
    # CORS — Updated for Cloudflare Pages & AinaReports
    # -------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://ainaprotocol.com",
            "https://www.ainaprotocol.com",
            "https://ainareports.com",
            "https://www.ainareports.com",
            settings.CLOUDFLARE_PAGES_DOMAIN,   # *.pages.dev
        ],
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

        print("\n📍 Registered /api/v1 Routes:\n")
        for route in app.routes:
            if route.path.startswith("/api/v1"):
                methods = ",".join(route.methods or [])
                print(f"➡️  {methods:10s} {route.path}")
        print("\n✅ Route log complete.\n")

    # -------------------------------------------------
    # Centralized error handling
    # -------------------------------------------------
    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException):
        if exc.status_code in (401, 403, 500):
            logger.warning(
                f"HTTP {exc.status_code} at {request.url} — {exc.detail}"
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception):
        logger.error("Unhandled error at %s", request.url, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # -------------------------------------------------
    # Register Routers
    # -------------------------------------------------
    app.include_router(auth_router,        prefix="/api/v1")
    app.include_router(signup_router,      prefix="/api/v1")
    app.include_router(admin_router,       prefix="/api/v1")
    app.include_router(user_access_router, prefix="/api/v1")

    # New Supabase-only routers
    app.include_router(buildings_router,   prefix="/api/v1")
    app.include_router(events_router,      prefix="/api/v1")
    app.include_router(documents_router,   prefix="/api/v1")

    # New daily admin email report
    app.include_router(admin_daily_router, prefix="/api/v1")

    # -------------------------------------------------
    # Root Route (redirect to Cloudflare auth page)
    # -------------------------------------------------
    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="https://ainaprotocol.com/auth/login.html")

    return app


# Create API instance
app = create_app()
