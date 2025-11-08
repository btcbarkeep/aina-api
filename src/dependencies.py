# src/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from src.core.config import SECRET_KEY, ALGORITHM

security = HTTPBearer()

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
