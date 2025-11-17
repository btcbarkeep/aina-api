# core/permission_helpers.py

from fastapi import Depends, HTTPException
from dependencies.auth import get_current_user, CurrentUser
from core.permissions import ROLE_PERMISSIONS


# -----------------------------------------------------
# Build union: role permissions + per-user metadata overrides
# -----------------------------------------------------
def get_effective_permissions(user: CurrentUser) -> set:
    # Super admin bypass
    if user.role == "super_admin":
        return {"*"}

    role_perms = set(ROLE_PERMISSIONS.get(user.role, []))

    # User metadata overrides
    user_perms = set()
    raw = getattr(user, "permissions", [])
    if isinstance(raw, list):
        user_perms = set(raw)

    return role_perms.union(user_perms)


# -----------------------------------------------------
# Core permission evaluation
# -----------------------------------------------------
def has_permission(user: CurrentUser, permission: str) -> bool:
    effective = get_effective_permissions(user)

    # wildcard '*' means all permissions granted
    if "*" in effective:
        return True

    # contractor staff inherit contractor read/write rules
    if user.role in ["contractor", "contractor_staff"]:
        # They get the permissions defined in ROLE_PERMISSIONS
        # And additional user overrides
        return permission in effective

    return permission in effective


# -----------------------------------------------------
# FastAPI dependency wrapper
# -----------------------------------------------------
def requires_permission(permission: str):
    """
    Attach to any route:
        dependencies=[Depends(requires_permission("events:write"))]
    """

    def dependency(current_user: CurrentUser = Depends(get_current_user)):
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions: '{permission}' required"
            )
        return current_user

    return dependency
