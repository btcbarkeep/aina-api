from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError
import os

# ------------------------------------------------------------------
# Dynamically import constants so we never get path mismatch
# ------------------------------------------------------------------
try:
    from src.core.config import SECRET_KEY, ALGORITHM
except ModuleNotFoundError:
    # fallback for pytest local run
    from core.config import SECRET_KEY, ALGORITHM

def get_current_user(request: Request):
    """Validate JWT token from Authorization header."""
    auth_header = request.headers.get("authorization")
    print("🔍 [DEBUG] Header:", auth_header)

    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid token")

    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if not username or role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        print(f"✅ [DEBUG] Token decoded: sub={username}, role={role}")
        return {"username": username, "role": role}
    except JWTError as e:
        print(f"❌ [DEBUG] Token decode failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token decode failed: {e}")

def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Only allow admin users."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user

def get_active_user(current_user: dict = Depends(get_current_user)):
    """Allow any logged-in user."""
    return current_user
