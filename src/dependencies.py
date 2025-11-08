from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError
from src.core.config import SECRET_KEY, ALGORITHM

# ------------------------------------------------------------------
# Decode and verify JWT
# ------------------------------------------------------------------
def get_current_user(request: Request):
    """
    Validate JWT token from the Authorization header.
    Returns decoded payload with 'sub' and 'role'.
    """
    auth_header = request.headers.get("authorization")

    if not auth_header or not auth_header.lower().startswith("bearer "):
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
        return {"username": username, "role": role}
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate token",
        )


# ------------------------------------------------------------------
# Require Admin
# ------------------------------------------------------------------
def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Only allow admin users."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# ------------------------------------------------------------------
# Require any authenticated user
# ------------------------------------------------------------------
def get_active_user(current_user: dict = Depends(get_current_user)):
    """Allow any logged-in user."""
    return current_user
