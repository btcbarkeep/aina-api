# routers/contractor_events_supabase.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional

from dependencies.auth import (
    get_current_user,
    CurrentUser,
)

from core.supabase_client import get_supabase_client

router = APIRouter(
    prefix="/contractors",
    tags=["Contractor Events"]
)

# ============================================================
# GET — EVENTS BY CONTRACTOR
# Roles:
#   admin / super_admin  → can view any contractor's events
#   manager              → can view any contractor's events
#   contractor           → can ONLY view their own events
#   hoa                  → cannot view contractor events
# ============================================================
@router.get(
    "/{contractor_id}/events",
    summary="List all events tied to a contractor"
)
def list_contractor_events(
    contractor_id: str,
    building_id: Optional[str] = None,
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    # --------------------------------------------------------
    # PERMISSION CHECKS
    # --------------------------------------------------------
    allowed_roles = ["admin", "super_admin", "manager", "contractor"]

    if current_user.role not in allowed_roles:
        raise HTTPException(403, "You do not have permission to access this resource.")

    # Contractors can only view themselves
    if current_user.role == "contractor" and current_user.id != contractor_id:
        raise HTTPException(403, "Contractors may only view their own events.")

    # --------------------------------------------------------
    # QUERY — NOTE: events table uses created_by field
    # --------------------------------------------------------
    query = (
        client.table("events")
        .select("*")
        .eq("created_by", contractor_id)
        .order("occurred_at", desc=True)
    )

    # Optional filters
    if building_id:
        query = query.eq("building_id", building_id)
    if event_type:
        query = query.eq("event_type", event_type)
    if status:
        query = query.eq("status", status)

    try:
        result = query.execute()
        return result.data or []
    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")
