import os
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
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
from routers.units import router as units_router
from routers.events import router as events_router
from routers.documents import router as documents_router
from routers.documents_bulk import router as documents_bulk_router
from routers.document_email import router as document_email_router
from routers.contractors import router as contractors_router
from routers.contractor_events import router as contractor_events_router
from routers.pm_companies import router as pm_companies_router
from routers.aoao_organizations import router as aoao_organizations_router
from routers.requests import router as requests_router
from routers.messages import router as messages_router
from routers.financials import router as financials_router
from routers.reports import router as reports_router
from routers.subscriptions import router as subscriptions_router
from routers.stripe_webhooks import router as stripe_webhooks_router
from routers.manual_redact import router as manual_redact_router

from routers.uploads import router as uploads_router
from routers.health import router as health_router
from routers.public import router as public_router

# Admin Routers — restored
from routers.admin import router as admin_router
from routers.admin_daily import router as admin_daily_router

# ❌ REMOVED — legacy Admin Set Password Router
# from routers.admin_set_password import router as admin_set_password_router


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

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception):
        logger.error("Unhandled error at %s", request.url, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # -------------------------------------------------
    # Register Routers (NO /api/v1 prefix anymore)
    # -------------------------------------------------

    # Auth
    app.include_router(auth_router)
    app.include_router(signup_router)

    # Access Control
    app.include_router(user_access_router)

    # Core Data Routers
    app.include_router(buildings_router)
    app.include_router(events_router)
    app.include_router(documents_router)
    app.include_router(documents_bulk_router)
    app.include_router(document_email_router)
    app.include_router(contractors_router)
    app.include_router(contractor_events_router)
    app.include_router(units_router)
    app.include_router(pm_companies_router)
    app.include_router(aoao_organizations_router)
    app.include_router(requests_router)
    app.include_router(messages_router)
    app.include_router(reports_router)
    app.include_router(financials_router)
    app.include_router(subscriptions_router)

    # Admin
    app.include_router(admin_router)
    app.include_router(admin_daily_router)

    # ❌ REMOVED — Admin Set Password (Supabase now handles password setup/reset)
    # app.include_router(admin_set_password_router)

    # Uploads
    app.include_router(uploads_router)
    app.include_router(stripe_webhooks_router)
    app.include_router(manual_redact_router)

    # Health
    app.include_router(health_router)

    # Public (for ainareports.com)
    app.include_router(public_router)

    # -------------------------------------------------
    # Root Redirect (Cloudflare Frontend)
    # -------------------------------------------------
    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("https://ainaprotocol.com/auth/login.html")

    return app


# Create the global FastAPI instance
app = create_app()
