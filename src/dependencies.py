from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

# ------------------------------------------------------------------
# Import secret and algorithm
# ------------------------------------------------------------------
try:
    from src.core.config import SECRET_KEY, ALGORITHM
except ModuleNotFoundError:
    from core.config import SECRET_KEY, ALGORITHM

# ------------------------------------------------------------------
# Use HTTPBearer so Swagger uses Bearer token auth (not password)
# ------------------------------------------------------------------
bearer_scheme = HTTPBearer(auto_error=False)

# ------------------------------------------------------------------
# Decode and validate token
# ------------------------------------------------------------------
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """
    Validate JWT token and return user info (username + role).
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role", "user")

        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )

        return {"username": username, "role": role}

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {e}"
        )

# ------------------------------------------------------------------
# Restrict admin-only routes
# ------------------------------------------------------------------
def get_admin_user(current_user: dict = Depends(get_current_user)):
    """
    Only allow admin role to proceed.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required."
        )
    return current_user

# ------------------------------------------------------------------
# General user dependency
# ------------------------------------------------------------------
def get_active_user(current_user: dict = Depends(get_current_user)):
    """
    Allow any valid (authenticated) user.
    """
    return current_user
