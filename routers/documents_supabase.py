from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

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
    tags=["Documents"]
)

"""
DOCUMENTS ROUTER (SUPABASE-ONLY)

Manages document metadata for events/HOA records.
All IDs use Supabase UUIDs.

Role protection:
  - List: any authenticated user
  - Create: authenticated + (admin/manager OR building access)
  - Update: admin OR manager
  - Delete: admin OR manager
"""


# -----------------------------------------------------
# HELPER — Check building access
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
# HELPER — Get building_id from event_id
# -----------------------------------------------------
def get_event_building_id(event_id: str) -> str:
    client = get_supabase_client()

    event_result = (
        client.table("events")
        .select("building_id")
        .eq("id", event_id)
        .single()
        .execute()
    )

    if not event_result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    return event_result.data["building_id"]


# -----------------------------------------------------
# LIST DOCUMENTS (Any authenticated user)
# -----------------------------------------------------
@router.get("/supabase", summary="List Documents from Supabase")
def list_documents_supabase(
    limit: int = 100,
    current_user: CurrentUser = Depends(get_current_user)
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
# CREATE DOCUMENT
# Admin/Manager OR must have building access
# -----------------------------------------------------
@router.post(
    "/supabase",
    response_model=DocumentRead,
    summary="Create Document in Supabase"
)
def create_document_supabase(
    payload: DocumentCreate,
    current_user: CurrentUser = Depends(get_current_user)
):
    client = get_supabase_client()

    # 1️⃣ Get building_id for the event
    building_id = get_event_building_id(payload.event_id)

    # 2️⃣ Allow admins/managers immediately
    if current_user.role not in ["admin", "manager"]:
        # 3️⃣ Otherwise must have building access
        verify_user_building_access_supabase(current_user.user_id, building_id)

    # 4️⃣ Insert
    try:
        result = client.table("documents").insert(payload.dict()).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")


# -----------------------------------------------------
# UPDATE DOCUMENT (Admin + Manager)
# -----------------------------------------------------
@router.put("/supabase/{document_id}", summary="Update Document in Supabase")
def update_document_supabase(
    document_id: str,
    payload: DocumentUpdate,
    current_user: CurrentUser = Depends(get_current_user)
):
    requires_role(current_user, ["admin", "manager"])

    update_data = payload.dict(exclude_unset=True)

    result = update_record("documents", document_id, update_data)

    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return result["data"]


# -----------------------------------------------------
# DELETE DOCUMENT (Admin + Manager)
# -----------------------------------------------------
@router.delete("/supabase/{document_id}", summary="Delete Document in Supabase")
def delete_document_supabase(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user)
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

        return {
            "status": "deleted",
            "id": document_id,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase delete error: {e}")
