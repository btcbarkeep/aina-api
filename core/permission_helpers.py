# core/permission_helpers.py

from fastapi import Depends, HTTPException
from dependencies.auth import get_current_user
from core.permissions import ROLE_PERMISSIONS


# -----------------------------------------------------
# Core helper — check if user has permission
# -----------------------------------------------------
def has_permission(user_role: str, permission: str) -> bool:
    # super_admin bypass
    if user_role == "super_admin":
        return True

    allowed = ROLE_PERMISSIONS.get(user_role, [])
    return "*" in allowed or permission in allowed


# -----------------------------------------------------
# FastAPI dependency — requires_permission()
# -----------------------------------------------------
def requires_permission(permission: str):
    """
    Usage example:
        @router.post("/create", dependencies=[Depends(requires_permission("buildings:write"))])
    """

    def dependency(current_user = Depends(get_current_user)):
        if not has_permission(current_user.role, permission):
            raise HTTPException(status_code=403, detail="Permission denied")
        return current_user

    return dependency
