# dependencies/auth.py

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

from core.config import settings
from core.supabase_client import get_supabase_client

bearer_scheme = HTTPBearer()


# ============================================================
# Current User object returned to the frontend
# ============================================================
class CurrentUser(BaseModel):
    user_id: str
    email: str
    role: str
    full_name: Optional[str] = None
    organization_name: Optional[str] = None


# ============================================================
# Decode + Validate the JWT and lookup user in Supabase
# ============================================================
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> CurrentUser:

    token = credentials.credentials
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # -------------------------------------------------
    # Decode token
    # -------------------------------------------------
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise unauthorized

    email = payload.get("sub")
    user_id = payload.get("user_id")
    role_from_token = payload.get("role")

    if not email or not user_id:
        raise unauthorized

    # -------------------------------------------------
    # Bootstrap Admin Override
    # -------------------------------------------------
    if user_id == "bootstrap" and role_from_token == "admin":
        return CurrentUser(
            user_id="bootstrap",
            email=email,
            role="admin",
            full_name="Bootstrap Admin",
            organization_name="System",
        )

    # -------------------------------------------------
    # Lookup user in Supabase
    # -------------------------------------------------
    client = get_supabase_client()

    try:
        result = (
            client.table("users")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase error during user lookup: {str(e)}",
        )

    if not result.data:
        raise unauthorized

    user = result.data

    # -------------------------------------------------
    # Build CurrentUser object
    # -------------------------------------------------
    return CurrentUser(
        user_id=user["id"],
        email=user["email"],
        role=user.get("role", "hoa"),
        full_name=user.get("full_name"),
        organization_name=user.get("organization_name"),
    )


# ============================================================
# Role Requirement Wrapper
# ============================================================
def requires_role(required_role: str):
    def checker(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{required_role}' role",
            )
        return current_user
    return checker


# ============================================================
# Admin Requirement Wrapper (shortcut)
# ============================================================
def require_admin(current_user: CurrentUser = Depends(get_current_user)):
    """
    Shortcut dependency used in admin routes.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
