from typing import Optional, List
from datetime import datetime
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from supabase import Client

from core.supabase_client import get_supabase_client
from core.permissions import ROLE_PERMISSIONS  # role → permission map


bearer_scheme = HTTPBearer()


# ============================================================
# Current User Model (full backend identity)
# ============================================================
class CurrentUser(BaseModel):
    id: str                         # legacy accessor (still works)
    auth_user_id: str               # ⭐ NEW — guaranteed Supabase Auth UID
    email: str
    role: str

    full_name: Optional[str] = None
    organization_name: Optional[str] = None
    phone: Optional[str] = None
    contractor_id: Optional[str] = None
    aoao_organization_id: Optional[str] = None
    pm_company_id: Optional[str] = None

    # ⭐ Option A — per-user metadata overrides
    permissions: Optional[List[str]] = []
    
    # ⭐ Subscription info (optional, fetched separately if needed)
    subscription_tier: Optional[str] = None
    subscription_status: Optional[str] = None
    is_trial: Optional[bool] = None
    trial_ends_at: Optional[datetime] = None


# ============================================================
# AUTH DECODING (Supabase: validates JWT + fetches metadata)
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
    # Validate JWT via Supabase GoTrue
    # ---------------------------------------------------------
    try:
        auth_resp = client.auth.get_user(token)
        if not auth_resp or not auth_resp.user:
            raise unauthorized
        auth_user = auth_resp.user
    except Exception:
        raise unauthorized

    # ---------------------------------------------------------
    # Extract identity
    # ---------------------------------------------------------
    user_id = auth_user.id
    email = auth_user.email
    metadata = auth_user.user_metadata or {}

    if not email:
        raise unauthorized

    # ---------------------------------------------------------
    # SPECIAL OVERRIDES (system accounts)
    # ---------------------------------------------------------
    if metadata.get("cron") is True:
        return CurrentUser(
            id="cron",
            auth_user_id="cron",       # ⭐ NEW
            email=email,
            role="admin",
            full_name="Cron Job",
            permissions=["*"],
        )

    if metadata.get("bootstrap_admin") is True:
        return CurrentUser(
            id="bootstrap",
            auth_user_id="bootstrap",  # ⭐ NEW
            email=email,
            role="admin",
            full_name="Bootstrap Admin",
            permissions=["*"],
        )

    # ---------------------------------------------------------
    # NORMAL USER PATH
    # ---------------------------------------------------------
    role = metadata.get("role", "aoao")
    if role not in ROLE_PERMISSIONS:
        role = "aoao"

    extended_permissions = metadata.get("permissions", [])
    if not isinstance(extended_permissions, list):
        extended_permissions = []

    return CurrentUser(
        id=user_id,
        auth_user_id=user_id,               # ⭐ NEW – the important line!
        email=email,
        role=role,
        full_name=metadata.get("full_name"),
        organization_name=metadata.get("organization_name"),
        phone=metadata.get("phone"),
        contractor_id=metadata.get("contractor_id"),
        aoao_organization_id=metadata.get("aoao_organization_id"),
        pm_company_id=metadata.get("pm_company_id"),
        permissions=extended_permissions,
    )


# ============================================================
# ROLE CHECKER (basic role list guard)
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
# PERMISSION CHECK (DELEGATES TO permission_helpers)
# ============================================================
def requires_permission(permission: str):
    """
    Thin wrapper so routes can still import from dependencies.auth.
    Real RBAC logic lives in core.permission_helpers.
    """
    from core.permission_helpers import requires_permission as new_checker
    return new_checker(permission)


# ============================================================
# OPTIONAL AUTHENTICATION (for hybrid endpoints)
# ============================================================
def get_optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[CurrentUser]:
    """
    Optional authentication dependency.
    Returns CurrentUser if valid token provided, None otherwise.
    Does not raise exceptions if no token provided.
    """
    if not credentials:
        return None
    
    try:
        return get_current_user(credentials)
    except HTTPException:
        # Invalid token - return None instead of raising
        return None
