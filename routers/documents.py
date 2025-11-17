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
# Helper — Check building access
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
        raise HTTPException(403, "User does not have access to this building.")


# -----------------------------------------------------
# Helper — event_id → building_id
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
# CREATE DOCUMENT
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

    # Non-admins must have access
    if current_user.role not in ["admin", "manager"]:
        verify_user_building_access_supabase(current_user.id, building_id)

    doc_data = sanitize(payload.model_dump())

    result = (
        client.table("documents")
        .insert(doc_data, returning="representation")
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(500, "Insert failed")

    return result.data


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

    try:
        result = (
            client.table("documents")
            .update(update_data)
            .eq("id", document_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    if not result.data:
        raise HTTPException(404, "Document not found")

    return result.data


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
        result = (
            client.table("documents")
            .delete(returning="representation")
            .eq("id", document_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")

    if not result.data:
        raise HTTPException(404, "Document not found")

    return {"status": "deleted", "id": document_id}
