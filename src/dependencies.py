import sys
from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError
from src.routers.auth import SECRET_KEY, ALGORITHM


# ------------------------------------------------------------------
# Helper: decode the JWT token from the Authorization header
# ------------------------------------------------------------------
def get_current_user(request: Request):
    """
    Validate JWT and return the decoded payload.
    Includes detailed debug output for troubleshooting token validation.
    """
    auth_header = request.headers.get("authorization")
    print("🔍 [DEBUG] Auth header received:", auth_header, flush=True)

    # Check header exists
    if not auth_header:
        print("❌ No Authorization header found.", flush=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token",
        )

    # Check Bearer prefix
    if not auth_header.lower().startswith("bearer "):
        print("❌ Authorization header does not start with 'Bearer '.", flush=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
        )

    # Extract JWT from header
    token = auth_header.split(" ")[1]
    print("🔐 [DEBUG] Token extracted:", token[:60] + "...", flush=True)

    try:
        print(f"🧩 [DEBUG] Using SECRET_KEY={SECRET_KEY!r}, ALGORITHM={ALGORITHM}", flush=True)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print("🧠 [DEBUG] Decoded payload:", payload, flush=True)

        if "sub" not in payload or "role" not in payload:
            print("❌ Missing sub/role in payload.", flush=True)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        return payload

    except JWTError as e:
        print("💥 [DEBUG] JWTError during decode:", str(e), flush=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token decode failed: {e}",
        )


# ------------------------------------------------------------------
# Restrict access to Admins only
# ------------------------------------------------------------------
def get_admin_user(current_user: dict = Depends(get_current_user)):
    """
    Only allow users with role='admin' to pass.
    """
    print("🧍 [DEBUG] Current user (for admin check):", current_user, flush=True)
    if current_user.get("role") != "admin":
        print("🚫 [DEBUG] User is not admin.", flush=True)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    print("✅ [DEBUG] Admin access granted.", flush=True)
    return current_user


# ------------------------------------------------------------------
# Basic "active user" dependency
# ------------------------------------------------------------------
def get_active_user(current_user: dict = Depends(get_current_user)):
    """
    Just ensures the user is authenticated (any role).
    """
    print("👤 [DEBUG] Active user validated:", current_user, flush=True)
    return current_user
