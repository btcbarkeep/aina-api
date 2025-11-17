from fastapi import Depends, HTTPException
from dependencies.auth import get_current_user, CurrentUser
from core.permissions import ROLE_PERMISSIONS


# -----------------------------------------------------
# Collect effective permissions:
#   • role-based permissions
#   • user-specific permission overrides from user_metadata["permissions"]
# -----------------------------------------------------
def get_effective_permissions(user: CurrentUser) -> set:
    # Super admin = master key
    if user.role == "super_admin":
        return {"*"}

    role_perms = set(ROLE_PERMISSIONS.get(user.role, []))

    # Handle optional per-user permission overrides
    user_overrides = set()
    raw = getattr(user, "permissions", None)

    if isinstance(raw, list):
        user_overrides = set(raw)

    return role_perms.union(user_overrides)


# -----------------------------------------------------
# Permission evaluation
# -----------------------------------------------------
def has_permission(user: CurrentUser, permission: str) -> bool:
    effective = get_effective_permissions(user)

    # Wildcard grants everything
    if "*" in effective:
        return True

    # Normal permission check
    return permission in effective


# -----------------------------------------------------
# FastAPI dependency wrapper
# -----------------------------------------------------
def requires_permission(permission: str):
    """
    Usage:
        @router.post("/", dependencies=[Depends(requires_permission("events:write"))])
    """

    def dependency(current_user: CurrentUser = Depends(get_current_user)):
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions: '{permission}' required"
            )
        return current_user

    return dependency
