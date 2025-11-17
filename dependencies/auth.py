from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from supabase import Client

from core.config import settings
from core.supabase_client import get_supabase_client
from core.roles import ROLE_PERMISSIONS  # Your existing role/permission map

bearer_scheme = HTTPBearer()


# ============================================================
# Current User Model (returned to backend + frontend)
# ============================================================
class CurrentUser(BaseModel):
    id: str
    email: str
    role: str
    full_name: Optional[str] = None
    organization_name: Optional[str] = None
    phone: Optional[str] = None
    contractor_id: Optional[str] = None


# ============================================================
# Decode token + resolve user from Supabase Auth
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
    # Attempt Supabase JWT validation
    # (Supabase will reject invalid/expired tokens automatically)
    # ---------------------------------------------------------
    try:
        auth_resp = client.auth.get_user(token)
        if not auth_resp or not auth_resp.user:
            raise unauthorized
        supabase_user = auth_resp.user
    except Exception:
        raise unauthorized

    # Extract core values
    user_id = supabase_user.id
    email = supabase_user.email

    if not email:
        raise unauthorized

    metadata = supabase_user.user_metadata or {}

    # ---------------------------------------------------------
    # CRON TOKEN OVERRIDE
    # ---------------------------------------------------------
    if metadata.get("cron") is True:
        return CurrentUser(
            id="cron",
            email=email,
            role="admin",
            full_name="Cron Job",
            organization_name="System",
            phone=None,
            contractor_id=None,
        )

    # ---------------------------------------------------------
    # BOOTSTRAP ADMIN OVERRIDE
    # ---------------------------------------------------------
    if metadata.get("bootstrap_admin") is True:
        return CurrentUser(
            id="bootstrap",
            email=email,
            role="admin",
            full_name="Bootstrap Admin",
            organization_name="System",
            phone=None,
            contractor_id=None,
        )

    # ---------------------------------------------------------
    # Normal Supabase user path
    # ---------------------------------------------------------

    # Pull role and custom data from user_metadata
    role = metadata.get("role", "hoa")
    full_name = metadata.get("full_name")
    organization_name = metadata.get("organization_name")
    phone = metadata.get("phone")
    contractor_id = metadata.get("contractor_id")

    # Validate role
    if role not in ROLE_PERMISSIONS:
        role = "hoa"

    return CurrentUser(
        id=user_id,
        email=email,
        role=role,
        full_name=full_name,
        organization_name=organization_name,
        phone=phone,
        contractor_id=contractor_id,
    )


# ============================================================
# Role Requirement Wrapper
# ============================================================
def requires_role(allowed_roles: list[str]):
    """
    Enforce that the current user's role is in the allowed roles.
    """
    def checker(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {allowed_roles}",
            )
        return current_user
    return checker


# ============================================================
# Permission System (fine-grained RBAC)
# ============================================================
def has_permission(role: str, permission: str) -> bool:
    """
    Check if a role has a permission.
    Supports "*" (full access).
    """
    allowed = ROLE_PERMISSIONS.get(role, [])

    if "*" in allowed:
        return True

    return permission in allowed


def requires_permission(permission: str):
    """
    FastAPI dependency wrapper for fine-grained permission checks.
    Example:
        @router.post("/", dependencies=[Depends(requires_permission("events:write"))])
    """
    def checker(current_user: CurrentUser = Depends(get_current_user)):
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {permission}",
            )
        return current_user

    return checker
