# routers/events.py

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
from core.logging_config import logger
from models.event import EventCreate, EventUpdate, EventRead
from models.event_comment import EventCommentCreate, EventCommentRead


router = APIRouter(
    prefix="/events",
    tags=["Events"],
)


# -----------------------------------------------------
# Helper — sanitize
# -----------------------------------------------------
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        if isinstance(v, str) and v.strip() == "":
            clean[k] = None
        else:
            clean[k] = v
    return clean


# -----------------------------------------------------
# Check building access
# -----------------------------------------------------
def verify_user_building_access_supabase(user_id: str, building_id: str):
    client = get_supabase_client()
    result = (
        client.table("user_building_access")
        .select("id")
        .eq("user_id", user_id)
        .eq("building_id", building_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(403, "You do not have permission for this building.")


# -----------------------------------------------------
# event_id → building
# -----------------------------------------------------
def get_event_building_id(event_id: str) -> str:
    client = get_supabase_client()
    result = (
        client.table("events")
        .select("building_id")
        .eq("id", event_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Event not found")
    return result.data["building_id"]


# -----------------------------------------------------
# Helper — Create event_units junction table entries
# -----------------------------------------------------
def create_event_units(event_id: str, unit_ids: list):
    if not unit_ids:
        return
    client = get_supabase_client()
    for unit_id in unit_ids:
        try:
            client.table("event_units").insert({
                "event_id": event_id,
                "unit_id": str(unit_id)
            }).execute()
        except Exception as e:
            error_msg = str(e).lower()
            if "duplicate" in error_msg or "unique" in error_msg:
                logger.debug(f"Duplicate event_unit relationship ignored: event_id={event_id}, unit_id={unit_id}")
            else:
                logger.warning(f"Failed to create event_unit relationship: {e}")
                raise HTTPException(500, f"Failed to create event_unit relationship: {e}")


# -----------------------------------------------------
# Helper — Create event_contractors junction table entries
# -----------------------------------------------------
def create_event_contractors(event_id: str, contractor_ids: list):
    if not contractor_ids:
        return
    client = get_supabase_client()
    for contractor_id in contractor_ids:
        try:
            client.table("event_contractors").insert({
                "event_id": event_id,
                "contractor_id": str(contractor_id)
            }).execute()
        except Exception as e:
            error_msg = str(e).lower()
            if "duplicate" in error_msg or "unique" in error_msg:
                logger.debug(f"Duplicate event_contractor relationship ignored: event_id={event_id}, contractor_id={contractor_id}")
            else:
                logger.warning(f"Failed to create event_contractor relationship: {e}")
                raise HTTPException(500, f"Failed to create event_contractor relationship: {e}")


# -----------------------------------------------------
# Helper — Update event_units junction table (replace all)
# -----------------------------------------------------
def update_event_units(event_id: str, unit_ids: list):
    client = get_supabase_client()
    client.table("event_units").delete().eq("event_id", event_id).execute()
    create_event_units(event_id, unit_ids)


# -----------------------------------------------------
# Helper — Update event_contractors junction table (replace all)
# -----------------------------------------------------
def update_event_contractors(event_id: str, contractor_ids: list):
    client = get_supabase_client()
    client.table("event_contractors").delete().eq("event_id", event_id).execute()
    create_event_contractors(event_id, contractor_ids)


# -----------------------------------------------------
# LIST EVENTS
# -----------------------------------------------------
@router.get("", summary="List Events", response_model=List[EventRead])
def list_events(limit: int = 200, current_user: CurrentUser = Depends(get_current_user)):
    client = get_supabase_client()
    result = (
        client.table("events")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# -----------------------------------------------------
# CREATE EVENT
# -----------------------------------------------------
@router.post(
    "",
    response_model=EventRead,
    dependencies=[Depends(requires_permission("events:write"))],
    summary="Create Event",
)
def create_event(payload: EventCreate, current_user: CurrentUser = Depends(get_current_user)):
    client = get_supabase_client()

    building_id = payload.building_id

    # Extract unit_ids and contractor_ids before sanitizing (they don't belong in events table)
    unit_ids = payload.unit_ids or []
    contractor_ids = payload.contractor_ids or []
    
    # If contractor user, add their contractor_id to the list
    if current_user.role == "contractor":
        if not getattr(current_user, "contractor_id", None):
            raise HTTPException(400, "Contractor account missing contractor_id.")
        # Add contractor_id to list if not already present
        if current_user.contractor_id not in contractor_ids:
            contractor_ids.append(current_user.contractor_id)

    # Sanitize and prepare event_data (exclude unit_ids and contractor_ids)
    event_data = sanitize(payload.model_dump(exclude={"unit_ids", "contractor_ids"}))
    event_data["created_by"] = current_user.id

    # Legacy: Keep contractor_id for backward compatibility (temporary)
    if current_user.role == "contractor":
        event_data["contractor_id"] = current_user.contractor_id

    # Building access check for non-admin, non-manager, non-contractor roles
    # Contractors have hardcoded access to post events for any building/unit
    contractor_roles = ["contractor", "contractor_staff"]
    if current_user.role not in ["admin", "manager"] + contractor_roles:
        verify_user_building_access_supabase(current_user.id, building_id)

    # Create event
    result = (
        client.table("events")
        .insert(event_data, returning="representation")
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(500, "Insert failed")

    event_id = result.data["id"]

    # Create junction table entries
    create_event_units(event_id, unit_ids)
    create_event_contractors(event_id, contractor_ids)

    return result.data


# -----------------------------------------------------
# UPDATE EVENT
# -----------------------------------------------------
@router.put(
    "/{event_id}",
    dependencies=[Depends(requires_permission("events:write"))],
    summary="Update Event",
)
def update_event(event_id: str, payload: EventUpdate, current_user: CurrentUser = Depends(get_current_user)):
    client = get_supabase_client()
    
    # Extract unit_ids and contractor_ids if provided
    unit_ids = payload.unit_ids if hasattr(payload, 'unit_ids') and payload.unit_ids is not None else None
    contractor_ids = payload.contractor_ids if hasattr(payload, 'contractor_ids') and payload.contractor_ids is not None else None
    
    # Prepare update_data (exclude unit_ids and contractor_ids)
    update_data = sanitize(payload.model_dump(exclude_unset=True, exclude={"unit_ids", "contractor_ids"}))
    
    # Contractors can ONLY update status, nothing else
    contractor_roles = ["contractor", "contractor_staff"]
    if current_user.role in contractor_roles:
        # Only allow status updates for contractors
        allowed_fields = {"status"}
        update_data = {k: v for k, v in update_data.items() if k in allowed_fields}
        
        if not update_data:
            raise HTTPException(400, "Contractors can only update event status.")
    
    # Update event table
    try:
        result = (
            client.table("events")
            .update(update_data)
            .eq("id", event_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    if not result.data:
        raise HTTPException(404, "Event not found")

    # Update junction tables if provided
    if unit_ids is not None:
        update_event_units(event_id, unit_ids)
    
    if contractor_ids is not None:
        update_event_contractors(event_id, contractor_ids)

    return result.data


# -----------------------------------------------------
# DELETE EVENT
# -----------------------------------------------------
@router.delete(
    "/{event_id}",
    dependencies=[Depends(requires_permission("events:write"))],
    summary="Delete Event",
)
def delete_event(event_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """
    Delete an event.
    Contractors CANNOT delete events (hardcoded restriction).
    """
    # Contractors cannot delete events
    contractor_roles = ["contractor", "contractor_staff"]
    if current_user.role in contractor_roles:
        raise HTTPException(403, "Contractors cannot delete events.")
    
    client = get_supabase_client()

    # Cannot delete if documents reference this event
    docs = (
        client.table("documents")
        .select("id")
        .eq("event_id", event_id)
        .execute()
    )

    if docs.data:
        raise HTTPException(400, "Cannot delete event: documents exist.")

    try:
        result = (
            client.table("events")
            .delete(returning="representation")
            .eq("id", event_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")

    if not result.data:
        raise HTTPException(404, "Event not found")

    return {"status": "deleted", "id": event_id}


# -----------------------------------------------------
# EVENT COMMENTS
# -----------------------------------------------------

@router.post(
    "/{event_id}/comments",
    response_model=EventCommentRead,
    summary="Add comment to event",
)
def create_event_comment(
    event_id: str,
    payload: EventCommentCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Add a comment to an event.
    Contractors have hardcoded access to comment on any event.
    """
    client = get_supabase_client()
    
    # Verify event exists
    event = (
        client.table("events")
        .select("id, building_id")
        .eq("id", event_id)
        .single()
        .execute()
    )
    
    if not event.data:
        raise HTTPException(404, "Event not found")
    
    # Contractors have hardcoded access to comment on any event
    contractor_roles = ["contractor", "contractor_staff"]
    if current_user.role not in ["admin", "manager"] + contractor_roles:
        # For other roles, check building access
        building_id = event.data["building_id"]
        verify_user_building_access_supabase(current_user.id, building_id)
    
    # Create comment (use event_id from path, ignore it in payload if present)
    comment_data = {
        "event_id": event_id,
        "user_id": current_user.id,
        "comment_text": payload.comment_text,
    }
    
    try:
        result = (
            client.table("event_comments")
            .insert(comment_data, returning="representation")
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to create comment: {e}")
    
    if not result.data:
        raise HTTPException(500, "Comment creation failed")
    
    return result.data


@router.get(
    "/{event_id}/comments",
    response_model=List[EventCommentRead],
    summary="Get comments for an event",
)
def get_event_comments(
    event_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get all comments for an event."""
    client = get_supabase_client()
    
    # Verify event exists
    event = (
        client.table("events")
        .select("id, building_id")
        .eq("id", event_id)
        .single()
        .execute()
    )
    
    if not event.data:
        raise HTTPException(404, "Event not found")
    
    # Contractors have hardcoded access to view comments on any event
    contractor_roles = ["contractor", "contractor_staff"]
    if current_user.role not in ["admin", "manager"] + contractor_roles:
        # For other roles, check building access
        building_id = event.data["building_id"]
        verify_user_building_access_supabase(current_user.id, building_id)
    
    try:
        result = (
            client.table("event_comments")
            .select("*")
            .eq("event_id", event_id)
            .order("created_at", desc=False)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch comments: {e}")
    
    return result.data or []
