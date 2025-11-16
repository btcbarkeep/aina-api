# routers/events_supabase.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List

from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser,
)

from core.supabase_client import get_supabase_client
from core.supabase_helpers import update_record

from models.event import EventCreate, EventUpdate, EventRead


router = APIRouter(
    prefix="/events",
    tags=["Events"],
)

"""
EVENTS ROUTER (SUPABASE-ONLY, SYNC CLIENT SAFE)

Fixes:
  ✓ No more .select("*") after insert/delete/update
  ✓ All inserts use returning="representation"
  ✓ All deletes use returning="representation"
  ✓ Comment insert updated
  ✓ Fully sanitized payloads
  ✓ Admin/Manager/Contractor logic intact
"""


# -----------------------------------------------------
# Helper — sanitize payloads ("" -> None)
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
# HELPER — Check if user has building access
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
        raise HTTPException(
            status_code=403,
            detail="You do not have permission for this building.",
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
        raise HTTPException(status_code=404, detail="Event not found")

    return result.data["building_id"]


# -----------------------------------------------------
# LIST EVENTS — Any authenticated user
# -----------------------------------------------------
@router.get(
    "/supabase",
    summary="List Events from Supabase",
    response_model=List[EventRead],
)
def list_events_supabase(
    limit: int = 200,
    current_user: CurrentUser = Depends(get_current_user),
):
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
        raise HTTPException(status_code=500, detail=f"Supabase fetch error: {e}")


# -----------------------------------------------------
# CREATE EVENT — Admin/Manager or building-access user
# -----------------------------------------------------
@router.post(
    "/supabase",
    response_model=EventRead,
    summary="Create Event in Supabase",
)
def create_event_supabase(
    payload: EventCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()
    building_id = payload.building_id

    # Admin / Manager: full access; others need building access
    if current_user.role not in ["admin", "manager"]:
        verify_user_building_access_supabase(current_user.user_id, building_id)

    try:
        event_data = sanitize(payload.model_dump())

        # Track creator
        event_data["created_by"] = current_user.user_id

        # Contractor rules
        if current_user.role == "contractor":
            if not current_user.contractor_id:
                raise HTTPException(
                    status_code=400,
                    detail="Contractor account missing contractor_id."
                )
            event_data["contractor_id"] = current_user.contractor_id

        elif current_user.role not in ["admin", "manager"]:
            # Owners, tenants, buyers, etc.
            event_data["contractor_id"] = None

        # Insert safely — NO .select("*")
        result = (
            client.table("events")
            .insert(event_data, returning="representation")
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Supabase insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")


# -----------------------------------------------------
# UPDATE EVENT — Admin OR Manager
# -----------------------------------------------------
@router.put(
    "/supabase/{event_id}",
    summary="Update Event in Supabase",
    response_model=EventRead,
    dependencies=[Depends(requires_role(["admin", "manager"]))],
)
def update_event_supabase(
    event_id: str,
    payload: EventUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    update_data = sanitize(payload.model_dump(exclude_unset=True))

    # Contractors cannot override identity
    if current_user.role == "contractor":
        update_data["contractor_id"] = current_user.contractor_id

    result = update_record("events", event_id, update_data)

    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return result["data"]


# -----------------------------------------------------
# DELETE EVENT — Admin OR Manager
# -----------------------------------------------------
@router.delete(
    "/supabase/{event_id}",
    summary="Delete Event in Supabase",
    dependencies=[Depends(requires_role(["admin", "manager"]))],
)
def delete_event_supabase(event_id: str):
    client = get_supabase_client()

    # Prevent deleting events with documents attached
    docs = (
        client.table("documents")
        .select("id")
        .eq("event_id", event_id)
        .execute()
    )

    if docs.data:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete event: documents exist for this event.",
        )

    result = (
        client.table("events")
        .delete(returning="representation")
        .eq("id", event_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    return {"status": "deleted", "id": event_id}


# -----------------------------------------------------
# ADD COMMENT — Admin OR Manager
# -----------------------------------------------------
@router.post(
    "/supabase/{event_id}/comment",
    summary="Add a comment/update to an event",
    dependencies=[Depends(requires_role(["admin", "manager"]))],
)
def add_event_comment(
    event_id: str,
    comment: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    # Confirm event exists
    building_id = get_event_building_id(event_id)

    # Admin always allowed; managers must have building access
    if current_user.role != "admin":
        verify_user_building_access_supabase(current_user.user_id, building_id)

    try:
        result = (
            client.table("event_comments")
            .insert(
                {
                    "event_id": event_id,
                    "user_id": current_user.user_id,
                    "comment": comment,
                },
                returning="representation",
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")
