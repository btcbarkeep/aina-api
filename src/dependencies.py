from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError
from src.routers.auth import SECRET_KEY, ALGORITHM

# ------------------------------------------------------------------
# Get current user from JWT
# ------------------------------------------------------------------
def get_current_user(request: Request):
    """
    Validate JWT from Authorization header and return the decoded payload.
    Expected header: Authorization: Bearer <token>
    """
    auth_header = request.headers.get("authorization")

    if not auth_header or not auth_header.lower().startswith("bearer "):
        # No header or wrong format
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token",
        )

    token = auth_header.split(" ", 1)[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if not username or role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        # Return a simple user dict
        return {"username": username, "role": role}
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate token",
        )

# ------------------------------------------------------------------
# Require admin
# ------------------------------------------------------------------
def get_admin_user(current_user: dict = Depends(get_current_user)):
    """
    Only allow users with role='admin'.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user

# ------------------------------------------------------------------
# Basic "active" user
# ------------------------------------------------------------------
def get_active_user(current_user: dict = Depends(get_current_user)):
    """
    Any authenticated user.
    """
    return current_user
