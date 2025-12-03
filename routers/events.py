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
# NEW — Validate multiple units belong to building
# -----------------------------------------------------
def validate_units_in_building(unit_ids: List[str], building_id: str):
    if not unit_ids:
        return
    
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
        # Support filtering by unit_id (legacy) or through event_units junction table
        # For now, check both legacy unit_id and junction table
        query = query.eq("unit_id", unit_id)

    query = query.order("created_at", desc=True).limit(limit)

    res = query.execute()
    events = res.data or []
    
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
    
    # Handle multiple units: prefer unit_ids over unit_id for backward compatibility
    unit_ids = payload.unit_ids if payload.unit_ids else ([payload.unit_id] if payload.unit_id else [])
    
    # Validate all units belong to building
    validate_units_in_building(unit_ids, building_id)

    # Handle multiple contractors: prefer contractor_ids over contractor_id
    contractor_ids = payload.contractor_ids if payload.contractor_ids else ([payload.contractor_id] if payload.contractor_id else [])

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


    # contractor role assignment logic
    # If user is contractor and no contractor_ids provided, add their contractor_id
    if current_user.role == "contractor":
        if not getattr(current_user, "contractor_id", None):
            raise HTTPException(400, "Contractor account missing contractor_id")
        # Add contractor's own ID if not already in list
        contractor_id_str = str(current_user.contractor_id)
        if contractor_id_str not in contractor_ids:
            contractor_ids.append(contractor_id_str)
    else:
        # Normalize contractor_ids
        normalized_contractor_ids = []
        for cid in contractor_ids:
            normalized = normalize_contractor_id(cid)
            if normalized:
                normalized_contractor_ids.append(normalized)
        contractor_ids = normalized_contractor_ids
    
    # Set legacy contractor_id for backward compatibility (first contractor if any)
    if contractor_ids:
        event_data["contractor_id"] = contractor_ids[0]
    else:
        event_data["contractor_id"] = None

    # Building access rules
    if current_user.role not in ["admin", "super_admin"]:
        verify_user_building_access(current_user.id, building_id)

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
def update_event(event_id: str, payload: EventUpdate):
    client = get_supabase_client()

    # Get building_id for validation
    building_id = get_event_building_id(event_id)
    
    # Handle unit_ids update
    unit_ids = None
    if payload.unit_ids is not None:
        unit_ids = payload.unit_ids
        validate_units_in_building(unit_ids, building_id)
    elif payload.unit_id is not None:
        # Backward compatibility: convert single unit_id to list
        unit_ids = [payload.unit_id]
        validate_units_in_building(unit_ids, building_id)
    
    # Handle contractor_ids update
    contractor_ids = None
    if payload.contractor_ids is not None:
        contractor_ids = payload.contractor_ids
        # Normalize contractor IDs
        normalized = []
        for cid in contractor_ids:
            normalized_cid = normalize_contractor_id(cid)
            if normalized_cid:
                normalized.append(normalized_cid)
        contractor_ids = normalized if normalized else None
    elif payload.contractor_id is not None:
        # Backward compatibility: convert single contractor_id to list
        normalized_cid = normalize_contractor_id(payload.contractor_id)
        contractor_ids = [normalized_cid] if normalized_cid else None

    # Prepare update data (exclude junction table fields)
    update_data = sanitize(payload.model_dump(exclude_unset=True, exclude={"unit_ids", "contractor_ids"}))
    update_data = ensure_datetime_strings(update_data)
    update_data = ensure_uuid_strings(update_data)
    
    # Set legacy contractor_id for backward compatibility
    if contractor_ids:
        update_data["contractor_id"] = contractor_ids[0]
    elif "contractor_id" in update_data:
        update_data["contractor_id"] = normalize_contractor_id(update_data.get("contractor_id"))

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
