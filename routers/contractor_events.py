# routers/contractor_events.py

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from dependencies.auth import get_current_user, CurrentUser
from core.permission_helpers import requires_permission

from core.supabase_client import get_supabase_client


router = APIRouter(
    prefix="/contractors",
    tags=["Contractor Events"],
)


# ============================================================
# GET — EVENTS BY CONTRACTOR
#
# Permissions:
#   • super_admin → can view any
#   • admin → can view any
#   • property_manager / hoa → can view any (per RBAC)
#   • contractor → can ONLY view their own events
#   • contractor_staff → can ONLY view their own events
#   • owner / tenant / buyer → deny
#
# Uses: contractors:read
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
        # Enforce: contractors can ONLY view their own events
        if getattr(current_user, "contractor_id", None) != contractor_id:
            raise HTTPException(
                403,
                "You may only view events associated with your own contractor account.",
            )

    # --------------------------------------------------------
    # FETCH EVENTS — NO .single(), no returning
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
        events = result.data or []

        return {"success": True, "data": events}

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")
