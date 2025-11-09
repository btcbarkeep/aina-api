# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from pydantic import BaseModel
from datetime import datetime, timedelta

from core.config import settings
from dependencies.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _create_access_token(username: str, role: str = "admin") -> str:
    """
    Create a JWT access token with an expiration and embedded role.
    """
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + expires_delta
    to_encode = {"sub": username, "role": role, "exp": expire}

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Simple admin login using credentials from environment variables.
    """
    if (
        form_data.username != settings.ADMIN_USERNAME
        or form_data.password != settings.ADMIN_PASSWORD
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # For now, all logins are admin role
    access_token = _create_access_token(username=form_data.username, role="admin")
    return Token(access_token=access_token)


@router.get("/me", response_model=CurrentUser)
async def read_me(current_user: CurrentUser = Depends(get_current_user)):
    """
    Returns user info derived from the JWT (username + role).
    """
    return current_user
