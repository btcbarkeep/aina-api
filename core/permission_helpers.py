from fastapi import Depends, HTTPException
from typing import List, Optional
from dependencies.auth import get_current_user, CurrentUser
from core.permissions import ROLE_PERMISSIONS
from core.supabase_client import get_supabase_client


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


# ============================================================
# UNIT-LEVEL PERMISSION HELPERS
# ============================================================

def is_admin(user: CurrentUser) -> bool:
    """Check if user is admin or super_admin (bypasses all restrictions)."""
    return user.role in ["admin", "super_admin"]


def require_admin(user: CurrentUser):
    """Raise exception if user is not admin/super_admin."""
    if not is_admin(user):
        raise HTTPException(
            status_code=403,
            detail="Admin or super_admin role required"
        )


def require_building_access(user: CurrentUser, building_id: str):
    """
    Check if user has access to a building.
    Admins bypass. AOAO roles check user_building_access table.
    """
    if is_admin(user):
        return
    
    client = get_supabase_client()
    
    # Check user_building_access table
    result = (
        client.table("user_building_access")
        .select("id")
        .eq("user_id", user.auth_user_id)
        .eq("building_id", building_id)
        .limit(1)
        .execute()
    )
    
    if not result.data:
        raise HTTPException(
            status_code=403,
            detail=f"You do not have access to building {building_id}"
        )


def require_unit_access(user: CurrentUser, unit_id: str):
    """
    Check if user has access to a unit.
    Admins bypass. Checks user_units_access table.
    """
    if is_admin(user):
        return
    
    client = get_supabase_client()
    
    # Check user_units_access table
    result = (
        client.table("user_units_access")
        .select("id")
        .eq("user_id", user.auth_user_id)
        .eq("unit_id", unit_id)
        .limit(1)
        .execute()
    )
    
    if not result.data:
        raise HTTPException(
            status_code=403,
            detail=f"You do not have access to unit {unit_id}"
        )


def require_units_access(user: CurrentUser, unit_ids: List[str]):
    """
    Check if user has access to all units in the list.
    Admins bypass. Checks user_units_access table for each unit.
    """
    if is_admin(user):
        return
    
    if not unit_ids:
        return
    
    client = get_supabase_client()
    
    # Get all units the user has access to
    result = (
        client.table("user_units_access")
        .select("unit_id")
        .eq("user_id", user.auth_user_id)
        .in_("unit_id", unit_ids)
        .execute()
    )
    
    accessible_unit_ids = {row["unit_id"] for row in (result.data or [])}
    
    # Check if user has access to all requested units
    missing_units = set(unit_ids) - accessible_unit_ids
    if missing_units:
        raise HTTPException(
            status_code=403,
            detail=f"You do not have access to units: {', '.join(missing_units)}"
        )


def require_event_access(user: CurrentUser, event_id: str):
    """
    Check if user has access to an event.
    Admins bypass. Checks via event_units → user_units_access.
    AOAO roles can access if event is in their building.
    """
    if is_admin(user):
        return
    
    client = get_supabase_client()
    
    # Get event's building_id
    event_result = (
        client.table("events")
        .select("building_id")
        .eq("id", event_id)
        .limit(1)
        .execute()
    )
    
    if not event_result.data:
        raise HTTPException(status_code=404, detail="Event not found")
    
    building_id = event_result.data[0]["building_id"]
    
    # AOAO roles can access events in their buildings
    if user.role in ["aoao", "aoao_staff"]:
        require_building_access(user, building_id)
        return
    
    # For other roles, check unit access via event_units
    event_units_result = (
        client.table("event_units")
        .select("unit_id")
        .eq("event_id", event_id)
        .execute()
    )
    
    unit_ids = [row["unit_id"] for row in (event_units_result.data or [])]
    
    if not unit_ids:
        # Event has no units, check building access
        require_building_access(user, building_id)
        return
    
    # Check if user has access to any unit in the event
    require_units_access(user, unit_ids)


def require_document_access(user: CurrentUser, document_id: str):
    """
    Check if user has access to a document.
    Admins bypass. Checks via document_units → user_units_access.
    AOAO roles can access if document is in their building.
    """
    if is_admin(user):
        return
    
    client = get_supabase_client()
    
    # Get document's building_id
    doc_result = (
        client.table("documents")
        .select("building_id")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    
    if not doc_result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    building_id = doc_result.data[0]["building_id"]
    
    # AOAO roles can access documents in their buildings
    if user.role in ["aoao", "aoao_staff"]:
        require_building_access(user, building_id)
        return
    
    # For other roles, check unit access via document_units
    document_units_result = (
        client.table("document_units")
        .select("unit_id")
        .eq("document_id", document_id)
        .execute()
    )
    
    unit_ids = [row["unit_id"] for row in (document_units_result.data or [])]
    
    if not unit_ids:
        # Document has no units, check building access
        require_building_access(user, building_id)
        return
    
    # Check if user has access to any unit in the document
    require_units_access(user, unit_ids)


def get_user_accessible_unit_ids(user: CurrentUser) -> List[str]:
    """
    Get list of unit IDs the user has access to.
    Admins return None (all units).
    """
    if is_admin(user):
        return None  # None means all units
    
    client = get_supabase_client()
    
    result = (
        client.table("user_units_access")
        .select("unit_id")
        .eq("user_id", user.auth_user_id)
        .execute()
    )
    
    return [row["unit_id"] for row in (result.data or [])]


def get_user_accessible_building_ids(user: CurrentUser) -> List[str]:
    """
    Get list of building IDs the user has access to.
    Admins return None (all buildings).
    """
    if is_admin(user):
        return None  # None means all buildings
    
    client = get_supabase_client()
    
    result = (
        client.table("user_building_access")
        .select("building_id")
        .eq("user_id", user.auth_user_id)
        .execute()
    )
    
    return [row["building_id"] for row in (result.data or [])]
