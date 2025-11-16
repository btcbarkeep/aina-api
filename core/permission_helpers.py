# core/permission_helpers.py

from fastapi import Depends, HTTPException
from dependencies.auth import get_current_user, CurrentUser
from core.permissions import ROLE_PERMISSIONS


# -----------------------------------------------------
# Core permission checker
# -----------------------------------------------------
def has_permission(user_role: str, permission: str) -> bool:
    # super_admin bypass
    if user_role == "super_admin":
        return True

    allowed = ROLE_PERMISSIONS.get(user_role, [])
    return "*" in allowed or permission in allowed


# -----------------------------------------------------
# FastAPI permission dependency
# -----------------------------------------------------
def requires_permission(permission: str):
    """
    Usage:
        @router.post("/create", dependencies=[Depends(requires_permission("buildings:write"))])
    """

    def dependency(current_user: CurrentUser = Depends(get_current_user)):
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions: requires '{permission}'"
            )
        return current_user

    return dependency
