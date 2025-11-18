from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from uuid import UUID

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
    # etc...
    # (UNCHANGED IMPORTS)
from models.event import EventCreate, EventUpdate, EventRead


router = APIRouter(
    prefix="/events",
    tags=["Events"],
)


# -----------------------------------------------------
# Helper — sanitize blanks → None (keeps UUID objects)
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
# Normalize contractor_id into UUID or None
# -----------------------------------------------------
def normalize_contractor_id(value) -> Optional[UUID]:
    if not value:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except Exception:
        return None


# -----------------------------------------------------
# Check building access (FIXED select)
# -----------------------------------------------------
def verify_user_building_access_supabase(user_id: str, building_id: str):
    client = get_supabase_client()
    result = (
        client.table("user_building_access")
        .select("*")      # <-- FIX: user_building_access has no id column
        .eq("user_id", user_id)
        .eq("building_id", building_id)
        .execute()
    )
    if not result.data:
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
# CREATE EVENT (FIXED access control)
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

    # created_by ALWAYS set
    event_data["created_by"] = current_user.id

    # Contractor linking rules
    if current_user.role == "contractor":
        if not getattr(current_user, "contractor_id", None):
            raise HTTPException(400, "Contractor account missing contractor_id.")
        event_data["contractor_id"] = current_user.contractor_id
    else:
        event_data["contractor_id"] = normalize_contractor_id(event_data.get("contractor_id"))

    # -------------------------------------------------
    # FIX: Only admin + super_admin bypass building access
    # -------------------------------------------------
    if current_user.role not in ["admin", "super_admin"]:
        verify_user_building_access_supabase(current_user.id, building_id)

    # Insert → fetch
    try:
        insert_res = client.table("events").insert(event_data).execute()
    except Exception as e:
        raise HTTPException(500, f"Supabase insert failed: {e}")

    if not insert_res.data:
        raise HTTPException(500, "Insert returned no data")

    event_id = insert_res.data[0]["id"]

    fetch_res = (
        client.table("events")
        .select("*")
        .eq("id", event_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Created event not found")

    return fetch_res.data[0]


# -----------------------------------------------------
# UPDATE EVENT
# -----------------------------------------------------
@router.put(
    "/{event_id}",
    dependencies=[Depends(requires_permission("events:write"))],
    summary="Update Event",
)
def update_event(event_id: str, payload: EventUpdate):
    client = get_supabase_client()

    update_data = sanitize(payload.model_dump(exclude_unset=True))

    if "contractor_id" in update_data:
        update_data["contractor_id"] = normalize_contractor_id(update_data["contractor_id"])

    try:
        update_res = (
            client.table("events")
            .update(update_data)
            .eq("id", event_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    if not update_res.data:
        raise HTTPException(404, "Event not found")

    fetch_res = (
        client.table("events")
        .select("*")
        .eq("id", event_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Updated event not found")

    return fetch_res.data[0]


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

    try:
        delete_res = (
            client.table("events")
            .delete()
            .eq("id", event_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")

    if not delete_res.data:
        raise HTTPException(404, "Event not found")

    return {"status": "deleted", "id": event_id}
