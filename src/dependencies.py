from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError
from src.routers.auth import SECRET_KEY, ALGORITHM

# ------------------------------------------------------------------
# Extract and verify JWT token
# ------------------------------------------------------------------
def get_current_user(request: Request):
    """Validate JWT and return payload dict."""
    auth_header = request.headers.get("authorization")
    print("🔍 [DEBUG] Auth header received:", auth_header)

    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid token")

    token = auth_header.split(" ")[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if "sub" not in payload or "role" not in payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return payload
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token decode failed: {e}")

# ------------------------------------------------------------------
# Admin guard
# ------------------------------------------------------------------
def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Only allow admin users."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user

# ------------------------------------------------------------------
# Basic active user dependency
# ------------------------------------------------------------------
def get_active_user(current_user: dict = Depends(get_current_user)):
    return current_user
