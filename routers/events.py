# routers/events.py

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
from core.supabase_helpers import safe_update

from models.event import EventCreate, EventUpdate, EventRead

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

    if current_user.role == "contractor":
        if not getattr(current_user, "contractor_id", None):
            raise HTTPException(400, "Contractor account missing contractor_id.")
        event_data["contractor_id"] = current_user.contractor_id

    if current_user.role not in ["admin", "manager"]:
        verify_user_building_access_supabase(current_user.id, building_id)

    result = (
        client.table("events")
        .insert(event_data, returning="representation")
        .execute()
    )

    if not result.data:
        raise HTTPException(500, "Insert failed")

    return result.data[0]


# -----------------------------------------------------
# UPDATE EVENT
# -----------------------------------------------------
@router.put(
    "/{event_id}",
    dependencies=[Depends(requires_permission("events:write"))],
    summary="Update Event",
)
def update_event(event_id: str, payload: EventUpdate):
    update_data = sanitize(payload.model_dump(exclude_unset=True))

    updated = safe_update("events", {"id": event_id}, update_data)
    if not updated:
        raise HTTPException(404, "Event not found")

    return updated


# -----------------------------------------------------
# DELETE EVENT
# -----------------------------------------------------
@router.delete(
    "/{event_id}",
    dependencies=[Depends(requires_permission("events:write"))],
    summary="Delete Event",
)
def delete_event(event_id: str):
    client = get_supabase_client()

    docs = (
        client.table("documents")
        .select("id")
        .eq("event_id", event_id)
        .execute()
    )

    if docs.data:
        raise HTTPException(400, "Cannot delete event: documents exist.")

    result = (
        client.table("events")
        .delete(returning="representation")
        .eq("id", event_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(404, "Event not found")

    return {"status": "deleted", "id": event_id}
