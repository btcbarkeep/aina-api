from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
from core.logging_config import logger
from core.utils import sanitize
from core.permission_helpers import (
    is_admin,
    require_building_access,
    require_units_access,
    require_event_access,
    get_user_accessible_unit_ids,
    get_user_accessible_building_ids,
)
from models.event import EventCreate, EventUpdate, EventRead


router = APIRouter(
    prefix="/events",
    tags=["Events"],
)


# -----------------------------------------------------
# datetime → isoformat
# -----------------------------------------------------
def ensure_datetime_strings(data: dict) -> dict:
    for k, v in data.items():
        if isinstance(v, datetime):
            data[k] = v.isoformat()
    return data


# -----------------------------------------------------
# UUID → string
# -----------------------------------------------------
def ensure_uuid_strings(data: dict) -> dict:
    for k, v in data.items():
        if isinstance(v, UUID):
            data[k] = str(v)
    return data


# -----------------------------------------------------
# contractor_id normalization
# -----------------------------------------------------
def normalize_contractor_id(value) -> Optional[str]:
    if not value:
        return None
    try:
        return str(UUID(str(value)))
    except Exception:
        return None


# -----------------------------------------------------
# building access
# -----------------------------------------------------
def verify_user_building_access(user_id: str, building_id: str):
    client = get_supabase_client()

    rows = (
        client.table("user_building_access")
        .select("*")
        .eq("user_id", user_id)
        .eq("building_id", building_id)
        .execute()
    ).data

    if not rows:
        raise HTTPException(403, "You do not have permission for this building.")


# -----------------------------------------------------
# event_id → building_id
# -----------------------------------------------------
def get_event_building_id(event_id: str) -> str:
    client = get_supabase_client()
    rows = (
        client.table("events")
        .select("building_id")
        .eq("id", event_id)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(404, "Event not found")

    return rows[0]["building_id"]


# -----------------------------------------------------
# NEW — Validate unit belongs to building
# -----------------------------------------------------
def validate_unit_in_building(unit_id: str, building_id: str):
    if not unit_id:
        return

    client = get_supabase_client()
    
    # First check if unit exists
    unit_rows = (
        client.table("units")
        .select("id, building_id")
        .eq("id", unit_id)
        .execute()
    ).data
    
    if not unit_rows:
        raise HTTPException(400, f"Unit {unit_id} does not exist")
    
    unit_building_id = unit_rows[0]["building_id"]
    if unit_building_id != building_id:
        raise HTTPException(400, f"Unit {unit_id} does not belong to the specified building")


# -----------------------------------------------------
# NEW — Validate multiple units belong to building
# -----------------------------------------------------
def validate_units_in_building(unit_ids: List[str], building_id: str):
    if not unit_ids:
        return
    
    # Check for duplicates
    if len(unit_ids) != len(set(unit_ids)):
        raise HTTPException(400, "Duplicate unit IDs are not allowed")
    
    client = get_supabase_client()
    for unit_id in unit_ids:
        validate_unit_in_building(unit_id, building_id)


# -----------------------------------------------------
# NEW — Create event_units junction table entries
# -----------------------------------------------------
def create_event_units(event_id: str, unit_ids: List[str]):
    if not unit_ids:
        return
    
    client = get_supabase_client()
    for unit_id in unit_ids:
        try:
            client.table("event_units").insert({
                "event_id": event_id,
                "unit_id": unit_id
            }).execute()
        except Exception as e:
            # Ignore duplicate key errors (unique constraint)
            if "duplicate" not in str(e).lower():
                logger.warning(f"Failed to create event_unit relationship: {e}")


# -----------------------------------------------------
# NEW — Create event_contractors junction table entries
# -----------------------------------------------------
def create_event_contractors(event_id: str, contractor_ids: List[str]):
    if not contractor_ids:
        return
    
    client = get_supabase_client()
    for contractor_id in contractor_ids:
        try:
            client.table("event_contractors").insert({
                "event_id": event_id,
                "contractor_id": contractor_id
            }).execute()
        except Exception as e:
            # Ignore duplicate key errors (unique constraint)
            if "duplicate" not in str(e).lower():
                logger.warning(f"Failed to create event_contractor relationship: {e}")


# -----------------------------------------------------
# NEW — Update event_units junction table (replace all)
# -----------------------------------------------------
def update_event_units(event_id: str, unit_ids: List[str]):
    client = get_supabase_client()
    
    # Delete existing relationships
    client.table("event_units").delete().eq("event_id", event_id).execute()
    
    # Create new relationships
    create_event_units(event_id, unit_ids)


# -----------------------------------------------------
# NEW — Update event_contractors junction table (replace all)
# -----------------------------------------------------
def update_event_contractors(event_id: str, contractor_ids: List[str]):
    client = get_supabase_client()
    
    # Delete existing relationships
    client.table("event_contractors").delete().eq("event_id", event_id).execute()
    
    # Create new relationships
    create_event_contractors(event_id, contractor_ids)


# -----------------------------------------------------
# NEW — Fetch units for an event
# -----------------------------------------------------
def get_event_units(event_id: str) -> list:
    client = get_supabase_client()
    
    # Join event_units with units table
    result = (
        client.table("event_units")
        .select("unit_id, units(*)")
        .eq("event_id", event_id)
        .execute()
    )
    
    units = []
    if result.data:
        for row in result.data:
            if row.get("units"):
                units.append(row["units"])
    
    return units


# -----------------------------------------------------
# NEW — Fetch contractors for an event
# -----------------------------------------------------
def get_event_contractors(event_id: str) -> list:
    client = get_supabase_client()
    
    # Join event_contractors with contractors table
    result = (
        client.table("event_contractors")
        .select("contractor_id, contractors(*)")
        .eq("event_id", event_id)
        .execute()
    )
    
    contractors = []
    if result.data:
        for row in result.data:
            if row.get("contractors"):
                contractor = row["contractors"]
                # Enrich contractor with roles
                contractor = enrich_contractor_with_roles(contractor)
                contractors.append(contractor)
    
    return contractors


# -----------------------------------------------------
# Helper — Enrich contractor with roles (centralized)
# -----------------------------------------------------
from core.contractor_helpers import enrich_contractor_with_roles


# -----------------------------------------------------
# NEW — Enrich event with units and contractors
# -----------------------------------------------------
def enrich_event_with_relations(event: dict) -> dict:
    """Add units and contractors arrays to event dict"""
    event_id = event.get("id")
    if not event_id:
        return event
    
    event["units"] = get_event_units(event_id)
    event["contractors"] = get_event_contractors(event_id)
    
    # Also add unit_ids and contractor_ids for convenience
    event["unit_ids"] = [u["id"] for u in event["units"]]
    event["contractor_ids"] = [c["id"] for c in event["contractors"]]
    
    return event


# -----------------------------------------------------
# Helper — Apply event filters
# -----------------------------------------------------
def apply_event_filters(query, params: dict):
    """Apply filtering to events query based on provided parameters."""
    client = get_supabase_client()
    
    # building_id filter
    if params.get("building_id"):
        query = query.eq("building_id", params["building_id"])
    
    # category filter
    if params.get("category"):
        query = query.eq("category_id", params["category"])
    
    # status filter
    if params.get("status"):
        query = query.eq("status", params["status"])
    
    # severity filter
    if params.get("severity"):
        query = query.eq("severity", params["severity"])
    
    # date range filters
    if params.get("start_date"):
        query = query.gte("occurred_at", params["start_date"])
    if params.get("end_date"):
        query = query.lte("occurred_at", params["end_date"])
    
    # unit_id filter (via event_units junction table)
    if params.get("unit_id"):
        # Get event IDs that have this unit
        event_units_result = (
            client.table("event_units")
            .select("event_id")
            .eq("unit_id", params["unit_id"])
            .execute()
        )
        event_ids = [row["event_id"] for row in (event_units_result.data or [])]
        if event_ids:
            query = query.in_("id", event_ids)
        else:
            # No events match, return empty result
            query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
    
    # unit_ids filter (via event_units junction table)
    if params.get("unit_ids"):
        unit_ids = params["unit_ids"]
        if unit_ids:
            # Get event IDs that have ANY of these units
            event_units_result = (
                client.table("event_units")
                .select("event_id")
                .in_("unit_id", unit_ids)
                .execute()
            )
            event_ids = list(set([row["event_id"] for row in (event_units_result.data or [])]))
            if event_ids:
                query = query.in_("id", event_ids)
            else:
                # No events match, return empty result
                query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
    
    # contractor_id filter (via event_contractors junction table)
    if params.get("contractor_id"):
        # Get event IDs that have this contractor
        event_contractors_result = (
            client.table("event_contractors")
            .select("event_id")
            .eq("contractor_id", params["contractor_id"])
            .execute()
        )
        event_ids = [row["event_id"] for row in (event_contractors_result.data or [])]
        if event_ids:
            query = query.in_("id", event_ids)
        else:
            # No events match, return empty result
            query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
    
    # contractor_ids filter (via event_contractors junction table)
    if params.get("contractor_ids"):
        contractor_ids = params["contractor_ids"]
        if contractor_ids:
            # Get event IDs that have ANY of these contractors
            event_contractors_result = (
                client.table("event_contractors")
                .select("event_id")
                .in_("contractor_id", contractor_ids)
                .execute()
            )
            event_ids = list(set([row["event_id"] for row in (event_contractors_result.data or [])]))
            if event_ids:
                query = query.in_("id", event_ids)
            else:
                # No events match, return empty result
                query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
    
    return query


# -----------------------------------------------------
# LIST EVENTS (with comprehensive filtering)
# -----------------------------------------------------
@router.get("", summary="List Events", response_model=List[EventRead])
def list_events(
    limit: int = Query(200, ge=1, le=1000, description="Maximum number of events to return (1-1000)"),
    building_id: Optional[str] = Query(None, description="Filter by building ID"),
    unit_id: Optional[str] = Query(None, description="Filter by single unit ID"),
    unit_ids: Optional[List[str]] = Query([], description="Filter by list of unit IDs"),
    contractor_id: Optional[str] = Query(None, description="Filter by single contractor ID"),
    contractor_ids: Optional[List[str]] = Query([], description="Filter by list of contractor IDs"),
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(None, description="Filter by status"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    start_date: Optional[datetime] = Query(None, description="Filter events from this date (ISO datetime)"),
    end_date: Optional[datetime] = Query(None, description="Filter events until this date (ISO datetime)"),
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    query = client.table("events").select("*")
    
    # Apply filters
    filter_params = {
        "building_id": building_id,
        "unit_id": unit_id,
        "unit_ids": unit_ids if unit_ids else None,
        "contractor_id": contractor_id,
        "contractor_ids": contractor_ids if contractor_ids else None,
        "category": category,
        "status": status,
        "severity": severity,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }
    
    query = apply_event_filters(query, filter_params)
    query = query.order("created_at", desc=True).limit(limit)

    res = query.execute()
    events = res.data or []
    
    # Apply permission-based filtering for non-admin users
    if not is_admin(current_user):
        accessible_unit_ids = get_user_accessible_unit_ids(current_user)
        accessible_building_ids = get_user_accessible_building_ids(current_user)
        
        filtered_events = []
        for event in events:
            event_building_id = event.get("building_id")
            
            # AOAO roles: filter by building access
            if current_user.role in ["aoao", "aoao_staff"]:
                if accessible_building_ids is None or event_building_id in accessible_building_ids:
                    filtered_events.append(event)
                continue
            
            # Other roles: filter by unit access
            # Get units for this event
            event_units_result = (
                client.table("event_units")
                .select("unit_id")
                .eq("event_id", event.get("id"))
                .execute()
            )
            event_unit_ids = [row["unit_id"] for row in (event_units_result.data or [])]
            
            if not event_unit_ids:
                # Event has no units, check building access
                if accessible_building_ids is None or event_building_id in accessible_building_ids:
                    filtered_events.append(event)
            else:
                # Check if user has access to any unit in the event
                if accessible_unit_ids is None or any(uid in accessible_unit_ids for uid in event_unit_ids):
                    filtered_events.append(event)
        
        events = filtered_events
    
    # Enrich each event with units and contractors
    enriched_events = [enrich_event_with_relations(event) for event in events]
    
    return enriched_events


# -----------------------------------------------------
# CREATE EVENT (now supports unit_id)
# -----------------------------------------------------
@router.post(
    "",
    response_model=EventRead,
    dependencies=[Depends(requires_permission("events:write"))],
)
def create_event(payload: EventCreate, current_user: CurrentUser = Depends(get_current_user)):
    client = get_supabase_client()

    building_id = payload.building_id
    
    # Validate building_id is not None (required by schema)
    if not building_id:
        raise HTTPException(400, "building_id is required and cannot be null")
    
    # Validate building exists
    building_rows = (
        client.table("buildings")
        .select("id")
        .eq("id", building_id)
        .execute()
    ).data
    if not building_rows:
        raise HTTPException(400, f"Building {building_id} does not exist")
    
    # Get unit_ids and contractor_ids from payload
    unit_ids = payload.unit_ids or []
    contractor_ids = payload.contractor_ids or []
    
    # Validate: all units must belong to the same building
    if unit_ids:
        validate_units_in_building(unit_ids, building_id)
        # Remove duplicates
        unit_ids = list(dict.fromkeys(unit_ids))  # Preserves order while removing duplicates
    
    # Validate: all contractors must exist
    if contractor_ids:
        # Check for duplicates
        if len(contractor_ids) != len(set(contractor_ids)):
            raise HTTPException(400, "Duplicate contractor IDs are not allowed")
        
        normalized_contractor_ids = []
        for cid in contractor_ids:
            normalized = normalize_contractor_id(cid)
            if normalized:
                normalized_contractor_ids.append(normalized)
            else:
                raise HTTPException(400, f"Contractor {cid} does not exist or is invalid")
        
        # Verify contractors exist in database
        client = get_supabase_client()
        for cid in normalized_contractor_ids:
            contractor_rows = (
                client.table("contractors")
                .select("id")
                .eq("id", cid)
                .execute()
            ).data
            if not contractor_rows:
                raise HTTPException(400, f"Contractor {cid} does not exist")
        
        contractor_ids = normalized_contractor_ids
    
    # contractor role assignment logic
    # If user is contractor and no contractor_ids provided, add their contractor_id
    if current_user.role == "contractor":
        if not getattr(current_user, "contractor_id", None):
            raise HTTPException(400, "Contractor account missing contractor_id")
        # Add contractor's own ID if not already in list
        contractor_id_str = str(current_user.contractor_id)
        if contractor_id_str not in contractor_ids:
            contractor_ids.append(contractor_id_str)

    # JSON-safe payload (remove unit_ids and contractor_ids from event_data - they go to junction tables)
    event_data = sanitize(payload.model_dump(exclude={"unit_ids", "contractor_ids"}))
    event_data = ensure_datetime_strings(event_data)
    event_data = ensure_uuid_strings(event_data)

    # -----------------------------------------------------
    # Use the REAL Supabase Auth UID for created_by
    # (Prevents mismatches with auth.users table)
    # -----------------------------------------------------
    auth_user_id = getattr(current_user, "auth_user_id", None) or str(current_user.id)
    event_data["created_by"] = auth_user_id

    # Permission checks: ensure user has access to building and all units
    if not is_admin(current_user):
        # Check building access
        require_building_access(current_user, building_id)
        
        # Check unit access (if units provided)
        if unit_ids:
            # AOAO roles can create events for their building even without unit access
            if current_user.role not in ["aoao", "aoao_staff"]:
                require_units_access(current_user, unit_ids)

    # Insert event
    try:
        res = client.table("events").insert(event_data).execute()
        if not res.data:
            raise HTTPException(500, "Insert returned no data")

        event_id = res.data[0]["id"]

        # Create junction table entries for units
        create_event_units(event_id, unit_ids)
        
        # Create junction table entries for contractors
        create_event_contractors(event_id, contractor_ids)

        # Fetch created event with related units and contractors
        fetch = client.table("events").select("*").eq("id", event_id).execute()
        if not fetch.data:
            raise HTTPException(500, "Created event not found")

        event = fetch.data[0]
        
        # Enrich with units and contractors
        event = enrich_event_with_relations(event)

        return event
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Log the actual error and provide a helpful message
        error_msg = str(e)
        logger.error(f"Error creating event: {error_msg}", exc_info=True)
        
        # Check for common Supabase errors
        if "duplicate" in error_msg.lower():
            raise HTTPException(400, f"Event creation failed: duplicate entry")
        elif "foreign key" in error_msg.lower() or "violates foreign key" in error_msg.lower():
            raise HTTPException(400, f"Event creation failed: invalid reference (building_id, unit_id, or contractor_id)")
        elif "not null" in error_msg.lower() or "null value" in error_msg.lower():
            raise HTTPException(400, f"Event creation failed: required field is missing")
        else:
            raise HTTPException(500, f"Event creation failed: {error_msg}")


# -----------------------------------------------------
# UPDATE EVENT (now supports unit_id validation)
# -----------------------------------------------------
@router.put(
    "/{event_id}",
    dependencies=[Depends(requires_permission("events:write"))],
)
def update_event(event_id: str, payload: EventUpdate, current_user: CurrentUser = Depends(get_current_user)):
    client = get_supabase_client()

    # Permission check: ensure user has access to this event
    require_event_access(current_user, event_id)
    
    # Get building_id for validation
    building_id = get_event_building_id(event_id)
    
    unit_ids = None
    if payload.unit_ids is not None:
        unit_ids = payload.unit_ids
        if unit_ids:
            validate_units_in_building(unit_ids, building_id)
            # Remove duplicates
            unit_ids = list(dict.fromkeys(unit_ids))
    
    # Handle contractor_ids update
    contractor_ids = None
    if payload.contractor_ids is not None:
        contractor_ids = payload.contractor_ids
        if contractor_ids:
            # Check for duplicates
            if len(contractor_ids) != len(set(contractor_ids)):
                raise HTTPException(400, "Duplicate contractor IDs are not allowed")
            
            # Normalize and validate contractor IDs
            normalized = []
            for cid in contractor_ids:
                normalized_cid = normalize_contractor_id(cid)
                if normalized_cid:
                    normalized.append(normalized_cid)
                else:
                    raise HTTPException(400, f"Contractor {cid} does not exist or is invalid")
            
            # Verify contractors exist in database
            client = get_supabase_client()
            for cid in normalized:
                contractor_rows = (
                    client.table("contractors")
                    .select("id")
                    .eq("id", cid)
                    .execute()
                ).data
                if not contractor_rows:
                    raise HTTPException(400, f"Contractor {cid} does not exist")
            
            contractor_ids = normalized if normalized else None

    # Permission check for unit_ids if being updated
    if unit_ids is not None and unit_ids:
        if not is_admin(current_user):
            # AOAO roles can update events for their building even without unit access
            if current_user.role not in ["aoao", "aoao_staff"]:
                require_units_access(current_user, unit_ids)
    
    # Prepare update data (exclude junction table fields)
    update_data = sanitize(payload.model_dump(exclude_unset=True, exclude={"unit_ids", "contractor_ids"}))
    update_data = ensure_datetime_strings(update_data)
    update_data = ensure_uuid_strings(update_data)

    # Update
    res = client.table("events").update(update_data).eq("id", event_id).execute()
    if not res.data:
        raise HTTPException(404, "Event not found")

    # Update junction tables if provided
    if unit_ids is not None:
        update_event_units(event_id, unit_ids)
    
    if contractor_ids is not None:
        update_event_contractors(event_id, contractor_ids)

    # Fetch updated
    fetch = client.table("events").select("*").eq("id", event_id).execute()
    if not fetch.data:
        raise HTTPException(500, "Updated event not found")

    event = fetch.data[0]
    
    # Enrich with units and contractors
    event = enrich_event_with_relations(event)

    return event


# -----------------------------------------------------
# DELETE EVENT
# -----------------------------------------------------
@router.delete(
    "/{event_id}",
    dependencies=[Depends(requires_permission("events:write"))],
)
def delete_event(event_id: str):
    client = get_supabase_client()

    # Cannot delete event with documents
    docs = (
        client.table("documents")
        .select("id")
        .eq("event_id", event_id)
        .execute()
    )

    if docs.data:
        raise HTTPException(400, "Cannot delete event: documents exist.")

    res = client.table("events").delete().eq("id", event_id).execute()
    if not res.data:
        raise HTTPException(404, "Event not found")

    return {"status": "deleted", "id": event_id}



# ============================================================
# COMMENTS — Helpers
# ============================================================

ALLOWED_COMMENT_ROLES = {
    "admin",
    "super_admin",
    "aoao",
    "property_manager",
}

def get_event_creator(event_id: str) -> Optional[str]:
    client = get_supabase_client()
    rows = (
        client.table("events")
        .select("created_by")
        .eq("id", event_id)
        .limit(1)
        .execute()
    ).data
    if not rows:
        raise HTTPException(404, "Event not found")
    return rows[0]["created_by"]


def can_modify_comments(current_user: CurrentUser, event_creator_id: str) -> bool:
    """
    True if:
      - user is admin/super_admin/aoao/property_manager
      - OR user is the event creator
    """
    if current_user.role in ALLOWED_COMMENT_ROLES:
        return True
    if str(current_user.id) == str(event_creator_id):
        return True
    return False


# ============================================================
# GET — LIST COMMENTS FOR EVENT
# ============================================================
@router.get("/{event_id}/comments", summary="List comments for an event")
def list_event_comments(
    event_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    result = (
        client.table("event_comments")
        .select("*")
        .eq("event_id", event_id)
        .order("created_at", desc=True)
        .execute()
    )

    return result.data or []


# ============================================================
# POST — ADD COMMENT TO EVENT
# ============================================================
@router.post("/{event_id}/comments", summary="Add a comment to an event")
def add_event_comment(
    event_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    event_creator = get_event_creator(event_id)

    # Enforce permission
    if not can_modify_comments(current_user, event_creator):
        raise HTTPException(403, "You cannot comment on this event.")

    comment_text = payload.get("comment_text", "").strip()
    if not comment_text:
        raise HTTPException(400, "comment_text is required")

    insert_data = {
        "event_id": event_id,
        "user_id": str(current_user.id),
        "comment_text": comment_text,
    }

    res = client.table("event_comments").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(500, "Failed to insert comment")

    return res.data[0]


# ============================================================
# PUT — UPDATE COMMENT
# ============================================================
@router.put("/{event_id}/comments/{comment_id}", summary="Update a comment")
def update_event_comment(
    event_id: str,
    comment_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    # Fetch comment + event_creator
    comment_rows = (
        client.table("event_comments")
        .select("user_id")
        .eq("id", comment_id)
        .limit(1)
        .execute()
    ).data

    if not comment_rows:
        raise HTTPException(404, "Comment not found")

    comment_owner = comment_rows[0]["user_id"]
    event_creator = get_event_creator(event_id)

    # Permission check:
    #   Admin/AOAO/PM/Super OR the event creator OR the comment owner
    if not (
        current_user.role in ALLOWED_COMMENT_ROLES
        or str(current_user.id) == str(event_creator)
        or str(current_user.id) == str(comment_owner)
    ):
        raise HTTPException(403, "You cannot modify this comment.")

    update_text = payload.get("comment_text", "").strip()
    if not update_text:
        raise HTTPException(400, "comment_text is required")

    update_res = (
        client.table("event_comments")
        .update({"comment_text": update_text})
        .eq("id", comment_id)
        .execute()
    )

    return update_res.data[0] if update_res.data else {}


# ============================================================
# DELETE — DELETE COMMENT
# ============================================================
@router.delete("/{event_id}/comments/{comment_id}", summary="Delete a comment")
def delete_event_comment(
    event_id: str,
    comment_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    comment_rows = (
        client.table("event_comments")
        .select("user_id")
        .eq("id", comment_id)
        .limit(1)
        .execute()
    ).data

    if not comment_rows:
        raise HTTPException(404, "Comment not found")

    comment_owner = comment_rows[0]["user_id"]
    event_creator = get_event_creator(event_id)

    # Same rule as update
    if not (
        current_user.role in ALLOWED_COMMENT_ROLES
        or str(current_user.id) == str(event_creator)
        or str(current_user.id) == str(comment_owner)
    ):
        raise HTTPException(403, "You cannot delete this comment.")

    delete_res = (
        client.table("event_comments")
        .delete()
        .eq("id", comment_id)
        .execute()
    )

    return {"status": "deleted", "comment_id": comment_id}
