from fastapi import APIRouter, HTTPException, Depends

from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser,
)

from core.supabase_client import get_supabase_client
    from core.supabase_helpers import update_record

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
    if not client:
        raise HTTPException(500, "Supabase not configured")

    result = (
        client.table("user_building_access")
        .select("id")
        .eq("user_id", user_id)
        .eq("building_id", building_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            403,
            "User does not have access to this building.",
        )


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
# LIST DOCUMENTS (any authenticated user)
# -----------------------------------------------------
@router.get(
    "/supabase",
    summary="List Documents from Supabase",
)
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
        raise HTTPException(500, f"Supabase fetch error: {e}")


# -----------------------------------------------------
# CREATE DOCUMENT — Admin/Manager OR building-access user
# -----------------------------------------------------
@router.post(
    "/supabase",
    response_model=DocumentRead,
    summary="Create Document in Supabase",
)
def create_document_supabase(
    payload: DocumentCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    # Determine building ID for RBAC
    if payload.event_id:
        building_id = get_event_building_id(payload.event_id)
    elif payload.building_id:
        building_id = payload.building_id
    else:
        raise HTTPException(
            400,
            "Either event_id OR building_id must be provided.",
        )

    # Enforce building access for non-admin/manager
    if current_user.role not in ["admin", "manager"]:
        verify_user_building_access_supabase(current_user.id, building_id)

    try:
        doc_data = sanitize(payload.model_dump())

        result = (
            client.table("documents")
            .insert(doc_data, returning="representation")
            .execute()
        )

        if not result.data:
            raise HTTPException(500, "Insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(500, f"Supabase insert error: {e}")


# -----------------------------------------------------
# UPDATE DOCUMENT — admin + manager
# -----------------------------------------------------
@router.put(
    "/supabase/{document_id}",
    summary="Update Document in Supabase",
    dependencies=[Depends(requires_role(["admin", "manager"]))],
)
def update_document_supabase(
    document_id: str,
    payload: DocumentUpdate,
):
    update_data = sanitize(payload.model_dump(exclude_unset=True))

    result = update_record("documents", document_id, update_data)

    if result["status"] != "ok":
        raise HTTPException(500, result["detail"])

    return result["data"]


# -----------------------------------------------------
# DELETE DOCUMENT — admin + manager
# -----------------------------------------------------
@router.delete(
    "/supabase/{document_id}",
    summary="Delete Document in Supabase",
    dependencies=[Depends(requires_role(["admin", "manager"]))],
)
def delete_document_supabase(document_id: str):
    client = get_supabase_client()

    try:
        result = (
            client.table("documents")
            .delete(returning="representation")
            .eq("id", document_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(404, "Document not found")

        return {"status": "deleted", "id": document_id}

    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")
