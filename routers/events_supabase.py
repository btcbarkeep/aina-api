# routers/events.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from dependencies.auth import get_current_user
from core.supabase_client import get_supabase_client
from core.supabase_helpers import update_record
from dependencies.auth import requires_role


from models.event import EventCreate, EventUpdate, EventRead


router = APIRouter(
    prefix="/events",
    tags=["Events"]
)

"""
EVENTS ROUTER (SUPABASE-ONLY)

Handles all AOAO event logs, maintenance records, notices, etc.
All data stored directly in Supabase.
"""


# -----------------------------------------------------
# RBAC: Check if user has access to a building
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
            detail="You do not have permission for this building."
        )


# -----------------------------------------------------
# Helper: event_id → building_id
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
# LIST EVENTS
# -----------------------------------------------------
@router.get("/supabase", summary="List Events from Supabase")
def list_events_supabase(
    limit: int = 200,
    current_user: dict = Depends(get_current_user)
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
# CREATE EVENT
# -----------------------------------------------------
@router.post(
    "/supabase",
    response_model=EventRead,
    summary="Create Event in Supabase"
)
def create_event_supabase(
    payload: EventCreate,
    current_user: dict = Depends(get_current_user)
):
    client = get_supabase_client()

    # 1️⃣ RBAC check
    verify_user_building_access_supabase(
        current_user["username"],
        payload.building_id
    )

    # 2️⃣ Create record
    try:
        result = client.table("events").insert(payload.dict()).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Supabase insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")


# -----------------------------------------------------
# UPDATE EVENT
# -----------------------------------------------------
@router.put("/supabase/{event_id}", summary="Update Event in Supabase")
def update_event_supabase(
    event_id: str,
    payload: EventUpdate,
    current_user: dict = Depends(get_current_user)
):
    # Confirm user has access to the building that owns this event
    building_id = get_event_building_id(event_id)

    verify_user_building_access_supabase(
        current_user["username"],
        building_id
    )

    update_data = payload.dict(exclude_unset=True)

    result = update_record("events", event_id, update_data)

    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return result["data"]


# -----------------------------------------------------
# DELETE EVENT (Supabase)
# -----------------------------------------------------
@router.delete(
    "/supabase/{event_id}",
    summary="Delete Event in Supabase"
)
def delete_event_supabase(
    event_id: str,
    current_user: dict = Depends(get_current_user),
):
    client = get_supabase_client()

    # 1️⃣ Role requirement — admin only
    require_admin_role(current_user)

    # 2️⃣ Prevent orphaned docs
    try:
        docs = (
            client.table("documents")
            .select("id")
            .eq("event_id", event_id)
            .execute()
        )

        if docs.data:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete event: documents exist for this event."
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document check failed: {e}")

    # 3️⃣ Delete
    try:
        result = (
            client.table("events")
            .delete()
            .eq("id", event_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Event not found")

        return {
            "status": "deleted",
            "id": event_id,
            "message": f"Event {event_id} deleted."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase delete error: {e}")
