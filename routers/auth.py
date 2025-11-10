# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from pydantic import BaseModel
from datetime import datetime, timedelta

from core.config import settings
from dependencies.auth import CurrentUser, get_current_user

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
    responses={401: {"description": "Unauthorized"}, 403: {"description": "Forbidden"}},
)

"""
Auth endpoints handle JWT-based authentication for admin and user access,
including token generation via /login and identity verification via /me.
"""


# -----------------------------------------------------
# Token Schema
# -----------------------------------------------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# -----------------------------------------------------
# Token Utility
# -----------------------------------------------------
def _create_access_token(username: str, role: str = "admin") -> str:
    """Create a JWT access token with expiration and embedded role."""
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + expires_delta
    to_encode = {"sub": username, "role": role, "exp": expire}

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


# -----------------------------------------------------
# Login Endpoint (Simple Admin Auth)
# -----------------------------------------------------
@router.post("/login", response_model=Token, summary="Generate Access Token")
async def login(username: str, password: str):
    """
    Simple admin login using credentials from environment variables.
    Returns a JWT token to be used as Bearer auth for other endpoints.
    """
    if username != settings.ADMIN_USERNAME or password != settings.ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # For now, all logins are admin role
    access_token = _create_access_token(username=username, role="admin")
    return Token(access_token=access_token)


# -----------------------------------------------------
# Verify Current User
# -----------------------------------------------------
@router.get("/me", response_model=CurrentUser, summary="Validate Access Token")
async def read_me(current_user: CurrentUser = Depends(get_current_user)):
    """Returns the authenticated user's info (decoded from JWT)."""
    return current_user
