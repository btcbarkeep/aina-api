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
EVENTS ROUTER (SUPABASE-ONLY)

Roles:
  - List: any authenticated user
  - Create: admin or manager OR user must have building access
  - Update: admin or manager
  - Delete: admin or manager
  - Comment: admin or manager
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
# CREATE EVENT — Admin/Manager, or building-access user
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

        result = (
            client.table("events")
            .insert(event_data)
            .select("*")
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
):
    update_data = sanitize(payload.model_dump(exclude_unset=True))

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
def delete_event_supabase(
    event_id: str,
):
    client = get_supabase_client()

    # Prevent deleting events that have documents attached
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
        .delete()
        .eq("id", event_id)
        .select("*")
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

    # Confirm event exists & get building
    building_id = get_event_building_id(event_id)

    # Managers must have building access (admins bypass)
    if current_user.role != "admin":
        verify_user_building_access_supabase(current_user.user_id, building_id)

    try:
        result = (
            client.table("event_comments")
            .insert(
                {
                    "event_id": event_id,
                    "user_id": current_user.user_id,
                    "comment": comment,  # assumes column name is "comment"
                }
            )
            .select("*")
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=500, detail="Insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")
