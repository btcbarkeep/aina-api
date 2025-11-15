from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from dependencies.auth import get_current_user
from core.supabase_client import get_supabase_client
from core.supabase_helpers import update_record
from models.document import DocumentCreate, DocumentUpdate, DocumentRead

from dependencies.auth import requires_role

)


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
  - Create: authenticated + must have building access (via user_building_access)
  - Update: admin OR manager
  - Delete: admin OR manager
"""


# -----------------------------------------------------
# HELPER — Check building access for a user
# -----------------------------------------------------
def verify_user_building_access_supabase(user_id: str, building_id: str):
    """
    Checks if a user has permission to access a building.
    user_building_access: (user_id uuid, building_id uuid)
    """

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
    """
    Returns the building_id (uuid) for a given event.
    """

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
    current_user: dict = Depends(get_current_user)
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
        raise HTTPException(status_code=500, detail=f"Supabase fetch error: {e}")


# -----------------------------------------------------
# CREATE DOCUMENT (Authenticated + Building Access)
# -----------------------------------------------------
@router.post(
    "/supabase",
    response_model=DocumentRead,
    summary="Create Document in Supabase"
)
def create_document_supabase(
    payload: DocumentCreate,
    current_user: dict = Depends(get_current_user)
):
    client = get_supabase_client()

    # 1️⃣ Get building_id for event
    building_id = get_event_building_id(payload.event_id)  # uuid

    # 2️⃣ User must have building access
    verify_user_building_access_supabase(current_user["id"], building_id)

    # 3️⃣ Insert metadata
    try:
        result = client.table("documents").insert(payload.dict()).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Supabase insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")


# -----------------------------------------------------
# UPDATE DOCUMENT (Admin + Manager only)
# -----------------------------------------------------
@router.put("/supabase/{document_id}", summary="Update Document in Supabase")
def update_document_supabase(
    document_id: str,   # UUID
    payload: DocumentUpdate,
    current_user: dict = Depends(get_current_user)
):
    require_role(current_user, ["admin", "manager"])  # 🔒 RBAC

    update_data = payload.dict(exclude_unset=True)

    result = update_record("documents", document_id, update_data)

    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return result["data"]


# -----------------------------------------------------
# DELETE DOCUMENT (Admin + Manager only)
# -----------------------------------------------------
@router.delete("/supabase/{document_id}", summary="Delete Document in Supabase")
def delete_document_supabase(
    document_id: str,  # UUID
    current_user: dict = Depends(get_current_user)
):
    require_role(current_user, ["admin", "manager"])  # 🔒 RBAC

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
            "message": f"Document {document_id} successfully deleted."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase delete error: {e}")
