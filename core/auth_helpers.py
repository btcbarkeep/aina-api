# core/auth_helpers.py

from datetime import datetime
from fastapi import HTTPException

from core.supabase_client import get_supabase_client


# ============================================================
# 🔐 RBAC — REQUIRE ADMIN ROLE
# ============================================================
def require_admin_role(current_user: dict):
    """
    Ensures the current user is an admin.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required for this action.",
        )


# ============================================================
# 🔐 Supabase RBAC — Check building access
# ============================================================
def verify_user_building_access_supabase(user_id: str, building_id: str):
    """
    Checks if user has access to a specific building.
    Supabase table: user_building_access
    """
    client = get_supabase_client()

    try:
        result = (
            client.table("user_building_access")
            .select("id")
            .eq("user_id", user_id)
            .eq("building_id", building_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase access lookup failed: {e}",
        )

    if not result.data:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to access this building.",
        )


# ============================================================
# 🔐 Helper: Resolve event_id → building_id
# ============================================================
def get_event_building_id(event_id: str) -> str:
    """
    Fetches the building_id for a given event.
    """
    client = get_supabase_client()

    try:
        result = (
            client.table("events")
            .select("building_id")
            .eq("id", event_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase lookup failed: {e}",
        )

    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found.")

    return result.data["building_id"]


# ============================================================
# 🔐 Combined helper — can this user modify this event?
# ============================================================
def verify_user_event_permission(user_id: str, event_id: str):
    """
    Confirms user has access to the building associated with this event.
    """
    building_id = get_event_building_id(event_id)
    verify_user_building_access_supabase(user_id, building_id)
