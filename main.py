import os
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Ensure local imports resolve correctly
sys.path.append(os.path.dirname(__file__))

# Core / Config
from core.config import settings
from core.logging_config import logger

# -------------------------------------------------
# Routers: Data / Supabase-backed
# -------------------------------------------------
from routers.buildings_supabase import router as buildings_router
from routers.events_supabase import router as events_router
from routers.documents_supabase import router as documents_router

# Contractors (new)
from routers.contractors_supabase import router as contractors_router

# -------------------------------------------------
# Routers: Auth / Admin
# -------------------------------------------------
from routers.auth import router as auth_router
from routers.signup import router as signup_router
from routers.admin import router as admin_router
from routers.user_access import router as user_access_router
from routers.admin_daily import router as admin_daily_router

# -------------------------------------------------
# AWS Uploads
# -------------------------------------------------
from routers.uploads import router as uploads_router

# -------------------------------------------------
# Health
# -------------------------------------------------
from routers.health import router as health_router


# -------------------------------------------------
# Create Application
# -------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.5.0",
        description="Aina Protocol API — Supabase-powered Real Estate Reporting",
    )

    # -------------------------------------------------
    # CORS
    # -------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -------------------------------------------------
    # Startup Logic
    # -------------------------------------------------
    @app.on_event("startup")
    async def on_startup():
        logger.info("🚀 Starting Aina Protocol API")
        print("\n📍 Registered /api/v1 Routes:\n")
        for route in app.routes:
            if route.path.startswith("/api/v1"):
                methods = ",".join(route.methods or [])
                print(f"➡️ {methods:12s} {route.path}")
        print("\n✅ Route log complete.\n")

    # -------------------------------------------------
    # Error Handling
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
    # Register All Versioned Routers (/api/v1)
    # -------------------------------------------------

    # Auth + Signup
    app.include_router(auth_router,                  prefix="/api/v1")
    app.include_router(signup_router,                prefix="/api/v1")

    # Admin + Access Control
    app.include_router(admin_router,                 prefix="/api/v1")
    app.include_router(user_access_router,           prefix="/api/v1")

    # Supabase-backed Data Routers
    app.include_router(buildings_router,             prefix="/api/v1")
    app.include_router(events_router,                prefix="/api/v1")
    app.include_router(documents_router,             prefix="/api/v1")

    # Contractors (directory + event mapping)
    app.include_router(contractors_router,           prefix="/api/v1")

    # Daily admin automation
    app.include_router(admin_daily_router,           prefix="/api/v1")

    # S3 Uploads
    app.include_router(uploads_router,               prefix="/api/v1")

    # Health Checks
    app.include_router(health_router,                prefix="/api/v1")

    # -------------------------------------------------
    # Root — Redirect to Cloudflare Login
    # -------------------------------------------------
    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("https://ainaprotocol.com/auth/login.html")

    return app


# Create the application instance
app = create_app()
