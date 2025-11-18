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
# Helper — sanitize payloads ("" → None)
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
# Helper — Check building access (FIXED: no id column)
# -----------------------------------------------------
def verify_user_building_access_supabase(user_id: str, building_id: str):
    client = get_supabase_client()
    result = (
        client.table("user_building_access")
        .select("*")     # <-- FIXED: this table has no id column
        .eq("user_id", user_id)
        .eq("building_id", building_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(403, "User does not have access to this building.")


# -----------------------------------------------------
# Helper — event_id → building_id (SAFE)
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
# LIST DOCUMENTS
# -----------------------------------------------------
@router.get("", summary="List Documents")
def list_documents(limit: int = 100, current_user: CurrentUser = Depends(get_current_user)):
    client = get_supabase_client()
    result = (
        client.table("documents")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# -----------------------------------------------------
# CREATE DOCUMENT — SAFE 2-STEP INSERT
# -----------------------------------------------------
@router.post(
    "",
    response_model=DocumentRead,
    dependencies=[Depends(requires_permission("documents:write"))],
    summary="Create Document",
)
def create_document(payload: DocumentCreate, current_user: CurrentUser = Depends(get_current_user)):
    client = get_supabase_client()

    # Determine building
    if payload.event_id:
        building_id = get_event_building_id(payload.event_id)
    elif payload.building_id:
        building_id = payload.building_id
    else:
        raise HTTPException(400, "event_id OR building_id is required.")

    # FIXED: Only admin + super_admin bypass building access
    if current_user.role not in ["admin", "super_admin"]:
        verify_user_building_access_supabase(current_user.id, building_id)

    doc_data = sanitize(payload.model_dump())

    # Step 1 — Insert (NO .single(), NO .select())
    try:
        insert_res = client.table("documents").insert(doc_data).execute()
    except Exception as e:
        raise HTTPException(500, f"Supabase insert error: {e}")

    if not insert_res.data:
        raise HTTPException(500, "Insert returned no data")

    doc_id = insert_res.data[0]["id"]

    # Step 2 — Fetch newly created row
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
# UPDATE DOCUMENT — SAFE 2-STEP UPDATE
# -----------------------------------------------------
@router.put(
    "/{document_id}",
    summary="Update Document",
    dependencies=[Depends(requires_permission("documents:write"))],
)
def update_document(document_id: str, payload: DocumentUpdate):
    client = get_supabase_client()
    update_data = sanitize(payload.model_dump(exclude_unset=True))

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

    # Step 2 — Fetch updated row
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
# DELETE DOCUMENT — SAFE 2-STEP DELETE
# -----------------------------------------------------
@router.delete(
    "/{document_id}",
    summary="Delete Document",
    dependencies=[Depends(requires_permission("documents:write"))],
)
def delete_document(document_id: str):
    client = get_supabase_client()

    # Step 1 — Delete
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
