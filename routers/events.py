# routers/events.py

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,   # ⭐ NEW permission system
)

from core.supabase_client import get_supabase_client
from core.supabase_helpers import update_record

from models.event import EventCreate, EventUpdate, EventRead


router = APIRouter(
    prefix="/events",
    tags=["Events"],
)

# -----------------------------------------------------
# Helper — sanitize payloads
# -----------------------------------------------------
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        clean[k] = None if isinstance(v, str) and v.strip() == "" else v
    return clean


# -----------------------------------------------------
# HELPER — Check user → building access
# -----------------------------------------------------
def verify_user_building_access(user_id: str, building_id: str):
    client = get_supabase_client()

    result = (
        client.table("user_building_access")
        .select("id")
        .eq("user_id", user_id)
        .eq("building_id", building_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            403,
            "User does not have access to this building."
        )


# -----------------------------------------------------
# HELPER — Get building_id from event_id
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
@router.get(
    "",
    summary="List Events",
    response_model=List[EventRead],
    dependencies=[Depends(requires_permission("events:read"))],
)
def list_events(limit: int = 200):
    client = get_supabase_client()

    try:
        result = (
            client.table("events")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    except Exception as e:
        raise HTTPException(500, f"Supabase fetch error: {e}")


# -----------------------------------------------------
# CREATE EVENT
# -----------------------------------------------------
@router.post(
    "",
    response_model=EventRead,
    summary="Create Event",
    dependencies=[Depends(requires_permission("events:write"))],
)
def create_event(
    payload: EventCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    building_id = payload.building_id

    # Non-admin must have building access
    if current_user.role not in ["admin", "super_admin"]:
        verify_user_building_access(current_user.id, building_id)

    try:
        event_data = sanitize(payload.model_dump())
        event_data["created_by"] = current_user.id

        # Contractor: enforce contractor identity
        if current_user.role == "contractor":
            contractor_id = getattr(current_user, "contractor_id", None)
            if not contractor_id:
                raise HTTPException(
                    400,
                    "Contractor account missing contractor_id."
                )
            event_data["contractor_id"] = contractor_id

        result = (
            client.table("events")
            .insert(event_data, returning="representation")
            .execute()
        )

        if not result.data:
            raise HTTPException(500, "Insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(500, f"Supabase insert error: {e}")


# -----------------------------------------------------
# UPDATE EVENT
# -----------------------------------------------------
@router.put(
    "/{event_id}",
    summary="Update Event",
    response_model=EventRead,
    dependencies=[Depends(requires_permission("events:write"))],
)
def update_event(
    event_id: str,
    payload: EventUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    update_data = sanitize(payload.model_dump(exclude_unset=True))

    result = update_record("events", event_id, update_data)
    if result["status"] != "ok":
        raise HTTPException(500, result["detail"])

    return result["data"]


# -----------------------------------------------------
# DELETE EVENT
# -----------------------------------------------------
@router.delete(
    "/{event_id}",
    summary="Delete Event",
    dependencies=[Depends(requires_permission("events:write"))],
)
def delete_event(event_id: str):
    client = get_supabase_client()

    # Cannot delete events with attached documents
    docs = (
        client.table("documents")
        .select("id")
        .eq("event_id", event_id)
        .execute()
    )

    if docs.data:
        raise HTTPException(
            400,
            "Cannot delete event: documents exist for this event."
        )

    result = (
        client.table("events")
        .delete(returning="representation")
        .eq("id", event_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(404, "Event not found")

    return {"status": "deleted", "id": event_id}


# -----------------------------------------------------
# ADD COMMENT — requires events:write
# -----------------------------------------------------
@router.post(
    "/{event_id}/comment",
    summary="Add a comment to an event",
    dependencies=[Depends(requires_permission("events:write"))],
)
def add_event_comment(
    event_id: str,
    comment: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    # Ensure event exists & determine associated building
    building_id = get_event_building_id(event_id)

    # Non-admin must have building access
    if current_user.role not in ["admin", "super_admin"]:
        verify_user_building_access(current_user.id, building_id)

    try:
        result = (
            client.table("event_comments")
            .insert(
                {
                    "event_id": event_id,
                    "user_id": current_user.id,
                    "comment": comment,
                },
                returning="representation",
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(500, "Insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(500, f"Supabase insert error: {e}")
