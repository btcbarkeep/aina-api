import os
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# Ensure local imports resolve
sys.path.append(os.path.dirname(__file__))

# Core
from core.config import settings
from core.logging_config import logger

# -------------------------------------------------
# Routers — Updated (NO _supabase, NO /api/v1)
# -------------------------------------------------
from routers.auth import router as auth_router
from routers.signup import router as signup_router
from routers.user_access import router as user_access_router

from routers.buildings import router as buildings_router
from routers.units import router as units_router         # ⭐ NEW ⭐
from routers.events import router as events_router
from routers.documents import router as documents_router
from routers.documents_bulk import router as documents_bulk_router
from routers.contractors import router as contractors_router
from routers.contractor_events import router as contractor_events_router

from routers.uploads import router as uploads_router
from routers.health import router as health_router

# Admin Routers
from routers.admin import router as admin_router
from routers.admin_daily import router as admin_daily_router


# -------------------------------------------------
# Create the Application
# -------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
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
    # Startup logging
    # -------------------------------------------------
    @app.on_event("startup")
    async def on_startup():
        logger.info("🚀 Starting Aina Protocol API")
        print("\n📍 Registered Routes:\n")
        for route in app.routes:
            methods = ",".join(route.methods or [])
            print(f"➡️ {methods:10s} {route.path}")
        print("\n✅ Route log complete.\n")

    # -------------------------------------------------
    # Error handling
    # -------------------------------------------------
    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException):
        if exc.status_code in (401, 403, 500):
            logger.warning(
                f"HTTP {exc.status_code} at {request.url} — {exc.detail}"
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        """Handle Pydantic validation errors and JSON decode errors with better error messages."""
        errors = exc.errors()
        
        # Check for JSON decode errors and provide helpful guidance
        for error in errors:
            if error.get("type") == "json_invalid":
                error_pos = error.get("loc", [])
                if len(error_pos) > 1 and isinstance(error_pos[1], int):
                    pos = error_pos[1]
                    ctx_error = error.get("ctx", {}).get("error", "")
                    logger.warning(
                        f"Validation/JSON error at {request.url} — JSON decode error at position {pos}: {ctx_error}. "
                        f"This usually means unescaped quotes or missing commas in the JSON payload."
                    )
                else:
                    logger.warning(f"Validation/JSON error at {request.url} — {errors}")
            else:
                logger.warning(f"Validation error at {request.url} — {errors}")
        
        return JSONResponse(
            status_code=422,
            content={"detail": errors},
        )

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

    # Auth
    app.include_router(auth_router)
    app.include_router(signup_router)

    # Access Control
    app.include_router(user_access_router)

    # Core Data Routers
    app.include_router(buildings_router)
    app.include_router(units_router)             # ⭐ ADDED ⭐
    app.include_router(events_router)
    app.include_router(documents_router)
    app.include_router(documents_bulk_router)
    app.include_router(contractors_router)
    app.include_router(contractor_events_router)

    # Admin Tools
    app.include_router(admin_router)
    app.include_router(admin_daily_router)

    # Uploads
    app.include_router(uploads_router)

    # Health Check
    app.include_router(health_router)

    # -------------------------------------------------
    # Root Redirect (Cloudflare Frontend)
    # -------------------------------------------------
    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("https://ainaprotocol.com/auth/login.html")

    return app


# Create the global FastAPI instance
app = create_app()
