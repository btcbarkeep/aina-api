# routers/documents.py

from fastapi import APIRouter, HTTPException, Depends

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
from models.document import (
    DocumentCreate,
    DocumentUpdate,
    DocumentRead,
)

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)

# -----------------------------------------------------
# Helper — sanitize + UUID → string
# -----------------------------------------------------
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        if v is None:
            clean[k] = None
        elif isinstance(v, str):
            clean[k] = v.strip() or None
        else:
            clean[k] = str(v)
    return clean


# -----------------------------------------------------
# Building-level access check
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
# event_id → building_id, unit_id
# -----------------------------------------------------
def get_event_info(event_id: str):
    client = get_supabase_client()

    rows = (
        client.table("events")
        .select("building_id, unit_id")
        .eq("id", event_id)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(404, "Event not found")

    return rows[0]["building_id"], rows[0].get("unit_id")


# -----------------------------------------------------
# unit_id → building_id
# -----------------------------------------------------
def get_unit_building(unit_id: str) -> str:
    client = get_supabase_client()

    rows = (
        client.table("units")
        .select("building_id")
        .eq("id", unit_id)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(400, "Unit does not exist")

    return rows[0]["building_id"]


# -----------------------------------------------------
# LIST DOCUMENTS
# -----------------------------------------------------
@router.get("", summary="List Documents")
def list_documents(
    limit: int = 100,
    building_id: str | None = None,
    event_id: str | None = None,
    unit_id: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    query = client.table("documents").select("*")

    if building_id:
        query = query.eq("building_id", building_id)
    if event_id:
        query = query.eq("event_id", event_id)
    if unit_id:
        query = query.eq("unit_id", unit_id)

    res = query.order("created_at", desc=True).limit(limit).execute()
    return res.data or []


# -----------------------------------------------------
# CREATE DOCUMENT — now fully unit-aware
# -----------------------------------------------------
@router.post(
    "",
    response_model=DocumentRead,
    summary="Create Document",
    dependencies=[Depends(requires_permission("documents:write"))],
)
def create_document(payload: DocumentCreate, current_user: CurrentUser = Depends(get_current_user)):
    client = get_supabase_client()

    event_id = payload.event_id
    building_id = payload.building_id
    unit_id = payload.unit_id

    # -------------------------------------------------
    # Determine building + unit based on payload
    # -------------------------------------------------

    if event_id:
        # event defines building and possibly unit
        building_id, event_unit = get_event_info(event_id)

        # Use event's unit if not explicitly provided
        if not unit_id:
            unit_id = event_unit

    elif unit_id:
        # derive building from unit
        building_id = get_unit_building(unit_id)

    elif building_id:
        # OK: building only
        building_id = str(building_id)

    else:
        raise HTTPException(400, "Must provide event_id OR unit_id OR building_id.")

    # -------------------------------------------------
    # Access Control
    # -------------------------------------------------
    if current_user.role not in ["admin", "super_admin", "hoa"]:
        verify_user_building_access(current_user.id, building_id)

    # -------------------------------------------------
    # Prepare record
    # -------------------------------------------------
    doc_data = sanitize(payload.model_dump())

    doc_data["building_id"] = str(building_id)
    doc_data["unit_id"] = str(unit_id) if unit_id else None
    doc_data["event_id"] = str(event_id) if event_id else None
    doc_data["uploaded_by"] = str(current_user.id)

    # -------------------------------------------------
    # Insert → Fetch
    # -------------------------------------------------
    try:
        insert_res = client.table("documents").insert(doc_data).execute()
    except Exception as e:
        raise HTTPException(500, f"Supabase insert error: {e}")

    if not insert_res.data:
        raise HTTPException(500, "Insert returned no data")

    doc_id = insert_res.data[0]["id"]

    fetch_res = (
        client.table("documents")
        .select("*")
        .eq("id", doc_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Created document not found")

    return fetch_res.data[0]


# -----------------------------------------------------
# UPDATE DOCUMENT
# -----------------------------------------------------
@router.put(
    "/{document_id}",
    summary="Update Document",
    dependencies=[Depends(requires_permission("documents:write"))],
)
def update_document(document_id: str, payload: DocumentUpdate):
    client = get_supabase_client()

    update_data = sanitize(payload.model_dump(exclude_unset=True))

    # event_id changed → derive new building / unit
    if "event_id" in update_data and update_data["event_id"]:
        building_id, unit_id = get_event_info(update_data["event_id"])
        update_data["building_id"] = str(building_id)
        update_data["unit_id"] = str(unit_id) if unit_id else None

    # unit_id changed → derive new building
    elif "unit_id" in update_data and update_data["unit_id"]:
        building_id = get_unit_building(update_data["unit_id"])
        update_data["building_id"] = str(building_id)

    # building only changed → allow (rare)
    if "building_id" in update_data:
        update_data["building_id"] = str(update_data["building_id"])

    # Step 1 — Update
    try:
        update_res = (
            client.table("documents")
            .update(update_data)
            .eq("id", document_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    if not update_res.data:
        raise HTTPException(404, "Document not found")

    # Step 2 — Fetch updated
    fetch_res = (
        client.table("documents")
        .select("*")
        .eq("id", document_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Updated document not found")

    return fetch_res.data[0]


# -----------------------------------------------------
# DELETE DOCUMENT
# -----------------------------------------------------
@router.delete(
    "/{document_id}",
    summary="Delete Document",
    dependencies=[Depends(requires_permission("documents:write"))],
)
def delete_document(document_id: str):
    client = get_supabase_client()

    try:
        delete_res = (
            client.table("documents")
            .delete()
            .eq("id", document_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")

    if not delete_res.data:
        raise HTTPException(404, "Document not found")

    return {"status": "deleted", "id": document_id}
