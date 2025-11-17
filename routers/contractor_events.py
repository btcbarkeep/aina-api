# routers/contractor_events.py

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from dependencies.auth import get_current_user, CurrentUser
from core.permission_helpers import has_permission, requires_permission

from core.supabase_client import get_supabase_client
from core.supabase_helpers import safe_select
from core.utils import sanitize


router = APIRouter(
    prefix="/contractors",
    tags=["Contractor Events"],
)


# ============================================================
# GET — EVENTS BY CONTRACTOR
# Permissions:
#   • super_admin → can view any
#   • admin → can view any
#   • property_manager / hoa → can view any (per RBAC)
#   • contractor → can ONLY view their own events
#   • contractor_staff → can ONLY view their own events
#   • owner / tenant / buyer → never
#
# Uses "contractors:read"
# ============================================================
@router.get(
    "/{contractor_id}/events",
    summary="List all events tied to a contractor",
    dependencies=[Depends(requires_permission("contractors:read"))],
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
    # ROLE-SPECIFIC ACCESS CONTROL
    # --------------------------------------------------------
    contractor_roles = ["contractor", "contractor_staff"]

    if current_user.role in contractor_roles:
        # contractor/staff must match ID exactly
        if current_user.id != contractor_id:
            raise HTTPException(
                403,
                "You may only view events associated with your own contractor account."
            )

    # Example:
    # If RBAC someday allows restricting HOA or PM access,
    # it will automatically update via "contractors:read".

    # --------------------------------------------------------
    # FETCH EVENTS
    # events table uses "created_by" for contractor submissions
    # --------------------------------------------------------
    try:
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

        result = query.execute()

        return {"success": True, "data": result.data or []}

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")
