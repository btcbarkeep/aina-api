from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.openapi.models import APIKey, APIKeyIn
from fastapi.openapi.utils import get_openapi
from jose import jwt, JWTError
from core.config import settings


# -----------------------------------------------------
#  BEARER AUTH SCHEME (for Swagger + FastAPI security)
# -----------------------------------------------------
security = HTTPBearer(auto_error=True)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Validate JWT from the Bearer token and return user info.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")

        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")

        return {"username": username, "role": role}

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_active_user(current_user: dict = Depends(get_current_user)):
    """Allow any authenticated user."""
    return current_user


def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Restrict access to admin users only."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# -----------------------------------------------------
#  CUSTOM OPENAPI SCHEMA (pretty Swagger label)
# -----------------------------------------------------
def custom_openapi(app):
    """
    Override default OpenAPI schema to rename the Authorize label to 'Bearer Token'.
    """
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Aina Protocol API",
        version="0.3.0",
        description="Backend for Aina Protocol — blockchain-based condo and property reporting system.",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Paste your **Bearer token** here (e.g., `Bearer eyJhbGciOi...`).",
        }
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema
