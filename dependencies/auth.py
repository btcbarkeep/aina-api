# dependencies/auth.py

from typing import Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from supabase import Client

from core.config import settings
from core.supabase_client import get_supabase_client

# Role map (role → default permissions)
from core.permissions import ROLE_PERMISSIONS

bearer_scheme = HTTPBearer()


# ============================================================
# Current User Model
# — everything your backend needs after authentication
# ============================================================
class CurrentUser(BaseModel):
    id: str
    email: str
    role: str
    full_name: Optional[str] = None
    organization_name: Optional[str] = None
    phone: Optional[str] = None
    contractor_id: Optional[str] = None

    # ⭐ NEW — per-user overrides (Option A)
    permissions: Optional[List[str]] = []


# ============================================================
# AUTH DECODING (Supabase JWT)
# ============================================================
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:

    token = credentials.credentials

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    client: Client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase client not configured")

    # ---------------------------------------------------------
    # Validate token via Supabase GoTrue
    # ---------------------------------------------------------
    try:
        auth_resp = client.auth.get_user(token)
        if not auth_resp or not auth_resp.user:
            raise unauthorized
        auth_user = auth_resp.user
    except Exception:
        raise unauthorized

    # ---------------------------------------------------------
    # Extract identity + metadata
    # ---------------------------------------------------------
    user_id = auth_user.id
    email = auth_user.email
    metadata = auth_user.user_metadata or {}

    if not email:
        raise unauthorized

    # ---------------------------------------------------------
    # SPECIAL OVERRIDES
    # ---------------------------------------------------------
    if metadata.get("cron") is True:
        return CurrentUser(
            id="cron",
            email=email,
            role="admin",
            full_name="Cron Job",
            permissions=["*"],
        )

    if metadata.get("bootstrap_admin") is True:
        return CurrentUser(
            id="bootstrap",
            email=email,
            role="admin",
            full_name="Bootstrap Admin",
            permissions=["*"],
        )

    # ---------------------------------------------------------
    # NORMAL USER PATH
    # ---------------------------------------------------------
    role = metadata.get("role", "hoa")
    full_name = metadata.get("full_name")
    organization_name = metadata.get("organization_name")
    phone = metadata.get("phone")
    contractor_id = metadata.get("contractor_id")

    # ⭐ NEW — per-user permission overrides
    extended_permissions = metadata.get("permissions", [])
    if not isinstance(extended_permissions, list):
        extended_permissions = []

    # Validate role
    if role not in ROLE_PERMISSIONS:
        role = "hoa"

    # Return unified CurrentUser object
    return CurrentUser(
        id=user_id,
        email=email,
        role=role,
        full_name=full_name,
        organization_name=organization_name,
        phone=phone,
        contractor_id=contractor_id,
        permissions=extended_permissions,     # ⭐ Option A included
    )


# ============================================================
# ROLE CHECKER (rarely used now but we keep it)
# ============================================================
def requires_role(allowed_roles: list[str]):
    def checker(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {allowed_roles}",
            )
        return current_user
    return checker


# ============================================================
# BASE PERMISSION CHECK (legacy)
# — real permission logic now in core/permission_helpers.py
# ============================================================
def has_permission(role: str, permission: str) -> bool:
    allowed = ROLE_PERMISSIONS.get(role, [])

    if "*" in allowed:
        return True

    return permission in allowed


def requires_permission(permission: str):
    """
    Legacy wrapper. Real logic is now in core.permission_helpers.
    Provided only to maintain API compatibility.
    """
    from core.permission_helpers import requires_permission as new_checker
    return new_checker(permission)
