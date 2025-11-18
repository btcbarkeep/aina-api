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


# =============================================================================
# GET — EVENTS BY CONTRACTOR (unit-aware)
# =============================================================================
@router.get(
    "/{contractor_id}/events",
    summary="List all events tied to a contractor",
    dependencies=[Depends(requires_permission("contractors:read"))],
)
def list_contractor_events(
    contractor_id: str,
    building_id: Optional[str] = None,
    unit_id: Optional[str] = None,
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):

    client = get_supabase_client()

    # -------------------------------------------------------------------------
    # ROLE-BASED ACCESS CONTROL
    # -------------------------------------------------------------------------
    blocked_roles = ["owner", "tenant", "buyer", "seller", "other"]

    if current_user.role in blocked_roles:
        raise HTTPException(403, "You do not have permission to view contractor events.")

    contractor_roles = ["contractor", "contractor_staff"]

    if current_user.role in contractor_roles:
        # Contractors can only see their own events
        if getattr(current_user, "contractor_id", None) != contractor_id:
            raise HTTPException(
                403,
                "You may only view events associated with your own contractor account.",
            )

    # -------------------------------------------------------------------------
    # Ensure contractor exists
    # -------------------------------------------------------------------------
    contractor_rows = (
        client.table("contractors")
        .select("id, name")
        .eq("id", contractor_id)
        .limit(1)
        .execute()
    ).data

    if not contractor_rows:
        raise HTTPException(404, f"Contractor '{contractor_id}' not found.")

    # -------------------------------------------------------------------------
    # QUERY EVENTS — proper filtering & ordering
    # -------------------------------------------------------------------------
    try:
        query = (
            client.table("events")
            .select("*")
            .eq("contractor_id", contractor_id)
            .order("occurred_at", desc=True)
        )

        if building_id:
            query = query.eq("building_id", building_id)
        if unit_id:
            query = query.eq("unit_id", unit_id)
        if event_type:
            query = query.eq("event_type", event_type)
        if status:
            query = query.eq("status", status)

        result = query.execute()
        events = result.data or []

        return {
            "success": True,
            "contractor": contractor_rows[0],
            "count": len(events),
            "data": events,
        }

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")
