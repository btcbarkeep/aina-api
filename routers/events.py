# routers/events.py

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
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

    event_data = sanitize(payload.model_dump())
    event_data["created_by"] = current_user.id

    # Contractor linking
    if current_user.role == "contractor":
        if not getattr(current_user, "contractor_id", None):
            raise HTTPException(400, "Contractor account missing contractor_id.")
        event_data["contractor_id"] = current_user.contractor_id

    # Building access check for non-admin, non-manager, non-contractor roles
    # Contractors have hardcoded access to post events for any building/unit
    contractor_roles = ["contractor", "contractor_staff"]
    if current_user.role not in ["admin", "manager"] + contractor_roles:
        verify_user_building_access_supabase(current_user.id, building_id)

    result = (
        client.table("events")
        .insert(event_data, returning="representation")
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(500, "Insert failed")

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
    update_data = sanitize(payload.model_dump(exclude_unset=True))
    
    # Contractors can ONLY update status, nothing else
    contractor_roles = ["contractor", "contractor_staff"]
    if current_user.role in contractor_roles:
        # Only allow status updates for contractors
        allowed_fields = {"status"}
        update_data = {k: v for k, v in update_data.items() if k in allowed_fields}
        
        if not update_data:
            raise HTTPException(400, "Contractors can only update event status.")
    
    # For non-contractors, check if they're trying to modify fields (not just status)
    # This prevents contractors from modifying other fields even if they somehow bypass the above check
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
