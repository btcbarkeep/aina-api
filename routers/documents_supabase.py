from fastapi import APIRouter, HTTPException, Depends

from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser
)

from core.supabase_client import get_supabase_client
from core.supabase_helpers import update_record
from models.document import DocumentCreate, DocumentUpdate, DocumentRead


router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


# -----------------------------------------------------
# Helper — Check building access
# -----------------------------------------------------
def verify_user_building_access_supabase(user_id: str, building_id: str):
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    result = (
        client.table("user_building_access")
        .select("*")
        .eq("user_id", user_id)
        .eq("building_id", building_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=403,
            detail="User does not have access to this building."
        )


# -----------------------------------------------------
# Helper — event_id → building_id
# -----------------------------------------------------
def get_event_building_id(event_id: str) -> str:
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

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
# LIST DOCUMENTS
# -----------------------------------------------------
@router.get("/supabase", summary="List Documents from Supabase")
def list_documents_supabase(
    limit: int = 100,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    try:
        result = (
            client.table("documents")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase fetch error: {e}"
        )


# -----------------------------------------------------
# CREATE DOCUMENT (admin/manager OR building access)
# -----------------------------------------------------
@router.post(
    "/supabase",
    response_model=DocumentRead,
    summary="Create Document in Supabase"
)
def create_document_supabase(
    payload: DocumentCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    # Determine which building this document belongs to
    if payload.event_id:
        building_id = get_event_building_id(payload.event_id)

    elif payload.building_id:
        building_id = payload.building_id

    else:
        raise HTTPException(
            status_code=400,
            detail="Either event_id OR building_id must be provided."
        )

    # Gate access for non-admin users
    if current_user.role not in ["admin", "manager"]:
        verify_user_building_access_supabase(current_user.user_id, building_id)

    # Insert into Supabase
    try:
        result = client.table("documents").insert(payload.dict()).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase insert error: {e}"
        )


# -----------------------------------------------------
# UPDATE DOCUMENT (admin + manager only)
# -----------------------------------------------------
@router.put("/supabase/{document_id}", summary="Update Document in Supabase")
def update_document_supabase(
    document_id: str,
    payload: DocumentUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    requires_role(current_user, ["admin", "manager"])

    update_data = payload.dict(exclude_unset=True)

    result = update_record("documents", document_id, update_data)

    if result["status"] != "ok":
        raise HTTPException(
            status_code=500,
            detail=result["detail"]
        )

    return result["data"]


# -----------------------------------------------------
# DELETE DOCUMENT (admin + manager only)
# -----------------------------------------------------
@router.delete("/supabase/{document_id}", summary="Delete Document in Supabase")
def delete_document_supabase(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    requires_role(current_user, ["admin", "manager"])

    client = get_supabase_client()

    try:
        result = (
            client.table("documents")
            .delete()
            .eq("id", document_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Document not found")

        return {"status": "deleted", "id": document_id}

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase delete error: {e}"
        )
