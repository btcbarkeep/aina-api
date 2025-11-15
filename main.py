# main.py
import os
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# --------------------------------------------------------
# Ensure local imports always resolve correctly
# --------------------------------------------------------
sys.path.append(os.path.dirname(__file__))

# --------------------------------------------------------
# Local imports
# --------------------------------------------------------
from core.config import settings
from core.logging_config import logger
from database import create_db_and_tables

from routers import (
    api_router,
    user_access,
    admin,
    auth_password,
    signup,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.3.0",
        description="Aina Protocol API – Real Estate Data & AOAO Management",
    )

    # -------------------------------------------------
    # CORS
    # -------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://ainaprotocol.com",
            "https://www.ainaprotocol.com",
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
    # Centralized Error Logging
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
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled server error at %s", request.url, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # -------------------------------------------------
    # Versioned API Routers
    # -------------------------------------------------
    app.include_router(api_router, prefix="/api/v1")          # core buildings/events/documents
    app.include_router(user_access.router, prefix="/api/v1")  # user building assignments
    app.include_router(admin.router, prefix="/api/v1")        # admin: create accounts
    app.include_router(auth_password.router, prefix="/api/v1")# password setup
    app.include_router(signup.router, prefix="/api/v1")       # future: public signup flow


    # -------------------------------------------------
    # Root → redirect to Cloudflare login page
    # -------------------------------------------------
    from fastapi.responses import RedirectResponse

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="https://ainaprotocol.com/auth/login.html")

    return app


# --------------------------------------------------------
# Create the application instance
# --------------------------------------------------------
app = create_app()
