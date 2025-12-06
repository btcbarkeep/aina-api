# routers/contractor_events.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from core.logging_config import logger

from dependencies.auth import get_current_user, CurrentUser
from core.permission_helpers import requires_permission, is_admin, get_user_accessible_unit_ids, get_user_accessible_building_ids
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
        .select("id, company_name")
        .eq("id", contractor_id)
        .limit(1)
        .execute()
    ).data

    if not contractor_rows:
        raise HTTPException(404, f"Contractor '{contractor_id}' not found.")

    # -------------------------------------------------------------------------
    # QUERY EVENTS — via event_contractors junction table
    # -------------------------------------------------------------------------
    try:
        # Step 1: Get event IDs from event_contractors junction table
        event_contractors_result = (
            client.table("event_contractors")
            .select("event_id")
            .eq("contractor_id", contractor_id)
            .execute()
        )
        
        event_ids = [row["event_id"] for row in (event_contractors_result.data or [])]
        
        if not event_ids:
            # No events for this contractor
            return {
                "success": True,
                "contractor": contractor_rows[0],
                "count": 0,
                "data": [],
            }
        
        # Step 2: Query events using the event IDs
        query = (
            client.table("events")
            .select("*")
            .in_("id", event_ids)
            .order("occurred_at", desc=True)
        )

        # Apply filters
        if building_id:
            query = query.eq("building_id", building_id)
        if event_type:
            query = query.eq("event_type", event_type)
        if status:
            query = query.eq("status", status)

        result = query.execute()
        events = result.data or []
        
        # Step 3: Filter by unit_id if provided (via event_units junction table)
        if unit_id:
            # Get event IDs that have this unit
            event_units_result = (
                client.table("event_units")
                .select("event_id")
                .eq("unit_id", unit_id)
                .in_("event_id", event_ids)
                .execute()
            )
            unit_event_ids = {row["event_id"] for row in (event_units_result.data or [])}
            events = [e for e in events if e.get("id") in unit_event_ids]
        
        # Step 4: Apply permission-based filtering for non-admin users
        if not is_admin(current_user):
            accessible_unit_ids = get_user_accessible_unit_ids(current_user)
            accessible_building_ids = get_user_accessible_building_ids(current_user)
            
            # Batch fetch all event_units for all events (prevents N+1 queries)
            event_ids_to_check = [e.get("id") for e in events if e.get("id")]
            event_units_map = {}
            if event_ids_to_check:
                event_units_result = (
                    client.table("event_units")
                    .select("event_id, unit_id")
                    .in_("event_id", event_ids_to_check)
                    .execute()
                )
                if event_units_result.data:
                    for row in event_units_result.data:
                        event_id = row.get("event_id")
                        unit_id_val = row.get("unit_id")
                        if event_id and unit_id_val:
                            if event_id not in event_units_map:
                                event_units_map[event_id] = []
                            event_units_map[event_id].append(unit_id_val)
            
            # Filter events based on permissions
            filtered_events = []
            for event in events:
                event_id = event.get("id")
                event_building_id = event.get("building_id")
                event_unit_ids = event_units_map.get(event_id, [])
                
                # Check building access
                if accessible_building_ids is None or event_building_id in accessible_building_ids:
                    # If event has units, check unit access
                    if event_unit_ids:
                        if accessible_unit_ids is None or any(uid in accessible_unit_ids for uid in event_unit_ids):
                            filtered_events.append(event)
                    else:
                        # Event has no units, building access is sufficient
                        filtered_events.append(event)
            
            events = filtered_events
        
        # Step 5: Batch enrich events with relations (prevents N+1 queries)
        from core.batch_helpers import batch_enrich_events_with_relations
        enriched_events = batch_enrich_events_with_relations(events)

        return {
            "success": True,
            "contractor": contractor_rows[0],
            "count": len(enriched_events),
            "data": enriched_events,
        }

    except Exception as e:
        from core.errors import handle_supabase_error
        logger.error(f"Error fetching contractor events: {e}")
        raise handle_supabase_error(e, "Failed to fetch contractor events", 500)
