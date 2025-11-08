from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError
from src.routers.auth import SECRET_KEY, ALGORITHM


# ------------------------------------------------------------------
# Extract and verify JWT token
# ------------------------------------------------------------------
def get_current_user(request: Request):
    """
    Validate JWT and return payload dict.
    This version prints extra debug info to pinpoint the failure.
    """
    auth_header = request.headers.get("authorization")
    print("🔍 [DEBUG] Auth header received:", auth_header)

    if not auth_header:
        print("❌ No Authorization header found.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token",
        )

    if not auth_header.lower().startswith("bearer "):
        print("❌ Authorization header does not start with 'Bearer '.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
        )

    token = auth_header.split(" ")[1]
    print("🔐 [DEBUG] Token extracted:", token[:60] + "...")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print("🧠 [DEBUG] Decoded payload:", payload)

        if "sub" not in payload or "role" not in payload:
            print("❌ Missing sub/role in payload.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return payload
    except JWTError as e:
        print("💥 [DEBUG] JWTError during decode:", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token decode failed: {e}",
        )



# ------------------------------------------------------------------
# Admin guard
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
# Basic active user dependency
# ------------------------------------------------------------------
def get_active_user(current_user: dict = Depends(get_current_user)):
    return current_user
