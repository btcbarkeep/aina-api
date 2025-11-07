from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from typing import Optional
import os

# 🔐 Import shared values from auth
from src.routers.auth import SECRET_KEY, ALGORITHM

# OAuth2 scheme points to the new /auth/token route (used by Swagger UI)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """
    Decodes and validates JWT token from the Authorization header.
    Returns the username (the 'sub' field in JWT) if valid.
    Raises HTTP 401 if invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception


def get_active_user(current_user: str = Depends(get_current_user)) -> str:
    """
    Wrapper dependency to represent an 'active' authenticated user.
    Used to protect routes that require login.
    """
    return current_user
