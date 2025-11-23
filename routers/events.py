from fastapi import APIRouter, Depends, HTTPException
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
from models.event import EventCreate, EventUpdate, EventRead


router = APIRouter(
    prefix="/events",
    tags=["Events"],
)


# -----------------------------------------------------
# Helper — sanitize blanks → None
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
    rows = (
        client.table("units")
        .select("id")
        .eq("id", unit_id)
        .eq("building_id", building_id)
        .execute()
    ).data

    if not rows:
        raise HTTPException(400, "Unit does not belong to this building.")


# -----------------------------------------------------
# LIST EVENTS (with NEW unit filtering)
# -----------------------------------------------------
@router.get("", summary="List Events", response_model=List[EventRead])
def list_events(
    limit: int = 200,
    building_id: Optional[str] = None,
    unit_id: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    query = client.table("events").select("*")

    if building_id:
        query = query.eq("building_id", building_id)
    if unit_id:
        query = query.eq("unit_id", unit_id)

    query = query.order("created_at", desc=True).limit(limit)

    res = query.execute()
    return res.data or []


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
    unit_id = payload.unit_id

    # Validate building/unit match
    validate_unit_in_building(unit_id, building_id)

    # JSON-safe payload
    event_data = sanitize(payload.model_dump())
    event_data = ensure_datetime_strings(event_data)
    event_data = ensure_uuid_strings(event_data)

    # -----------------------------------------------------
    # Use the REAL Supabase Auth UID for created_by
    # (Prevents mismatches with auth.users table)
    # -----------------------------------------------------
    auth_user_id = getattr(current_user, "auth_user_id", None) or str(current_user.id)
    event_data["created_by"] = auth_user_id


    # contractor role assignment logic
    if current_user.role == "contractor":
        if not getattr(current_user, "contractor_id", None):
            raise HTTPException(400, "Contractor account missing contractor_id")
        event_data["contractor_id"] = str(current_user.contractor_id)

    else:
        cid = normalize_contractor_id(event_data.get("contractor_id"))
        event_data["contractor_id"] = cid

    # Building access rules
    if current_user.role not in ["admin", "super_admin"]:
        verify_user_building_access(current_user.id, building_id)

    # Insert event
    try:
        res = client.table("events").insert(event_data).execute()
        if not res.data:
            raise HTTPException(500, "Insert returned no data")

        event_id = res.data[0]["id"]

        # Fetch created event
        fetch = client.table("events").select("*").eq("id", event_id).execute()
        if not fetch.data:
            raise HTTPException(500, "Created event not found")

        return fetch.data[0]
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
def update_event(event_id: str, payload: EventUpdate):
    client = get_supabase_client()

    update_data = sanitize(payload.model_dump(exclude_unset=True))
    update_data = ensure_datetime_strings(update_data)
    update_data = ensure_uuid_strings(update_data)

    # If unit is being changed, validate it matches building
    if "unit_id" in update_data:
        # Need existing event to know its building
        building_id = get_event_building_id(event_id)
        validate_unit_in_building(update_data["unit_id"], building_id)

    # Normalize contractor_id
    if "contractor_id" in update_data:
        update_data["contractor_id"] = normalize_contractor_id(update_data["contractor_id"])

    # Update
    res = client.table("events").update(update_data).eq("id", event_id).execute()
    if not res.data:
        raise HTTPException(404, "Event not found")

    # Fetch updated
    fetch = client.table("events").select("*").eq("id", event_id).execute()
    if not fetch.data:
        raise HTTPException(500, "Updated event not found")

    return fetch.data[0]


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
    "hoa",
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
      - user is admin/super_admin/hoa/property_manager
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
    #   Admin/HOA/PM/Super OR the event creator OR the comment owner
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
