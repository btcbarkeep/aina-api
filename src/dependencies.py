from fastapi import Depends, HTTPException, Request, status
from jose import jwt, JWTError

from src.core.config import SECRET_KEY, ALGORITHM


def get_current_user(request: Request):
    """
    Validate JWT from the Authorization header and return the payload.
    Expected header: Authorization: Bearer <token>
    """
    auth_header = request.headers.get("authorization")
    print("🔍 [DEBUG] Auth header received:", auth_header)

    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token",
        )

    token = auth_header.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token decode failed: {e}",
        )

    # Minimal payload validation
    if "sub" not in payload or "role" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    return payload  # e.g. {"sub": "...", "role": "admin"}


def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Ensure the current user is an admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def get_active_user(current_user: dict = Depends(get_current_user)):
    """Any authenticated user."""
    return current_user
