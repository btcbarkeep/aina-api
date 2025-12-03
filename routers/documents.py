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
        elif isinstance(v, bool):
            clean[k] = v  # Preserve boolean values
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
# event_id → building_id
# -----------------------------------------------------
def get_event_info(event_id: str):
    """Get building_id for an event. Returns (building_id, None) for compatibility."""
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

    return rows[0]["building_id"], None


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
# NEW — Validate multiple units belong to building
# -----------------------------------------------------
def validate_units_in_building(unit_ids: list, building_id: str):
    if not unit_ids:
        return
    
    # Check for duplicates
    if len(unit_ids) != len(set(unit_ids)):
        raise HTTPException(400, "Duplicate unit IDs are not allowed")
    
    client = get_supabase_client()
    for unit_id in unit_ids:
        unit_building = get_unit_building(str(unit_id))
        if unit_building != building_id:
            raise HTTPException(400, f"Unit {unit_id} does not belong to the specified building")


# -----------------------------------------------------
# NEW — Create document_units junction table entries
# -----------------------------------------------------
def create_document_units(document_id: str, unit_ids: list):
    if not unit_ids:
        return
    
    client = get_supabase_client()
    for unit_id in unit_ids:
        try:
            client.table("document_units").insert({
                "document_id": document_id,
                "unit_id": str(unit_id)
            }).execute()
        except Exception as e:
            # Ignore duplicate key errors (unique constraint)
            if "duplicate" not in str(e).lower():
                raise HTTPException(500, f"Failed to create document_unit relationship: {e}")


# -----------------------------------------------------
# NEW — Create document_contractors junction table entries
# -----------------------------------------------------
def create_document_contractors(document_id: str, contractor_ids: list):
    if not contractor_ids:
        return
    
    client = get_supabase_client()
    for contractor_id in contractor_ids:
        try:
            client.table("document_contractors").insert({
                "document_id": document_id,
                "contractor_id": str(contractor_id)
            }).execute()
        except Exception as e:
            # Ignore duplicate key errors (unique constraint)
            if "duplicate" not in str(e).lower():
                raise HTTPException(500, f"Failed to create document_contractor relationship: {e}")


# -----------------------------------------------------
# NEW — Update document_units junction table (replace all)
# -----------------------------------------------------
def update_document_units(document_id: str, unit_ids: list):
    client = get_supabase_client()
    
    # Delete existing relationships
    client.table("document_units").delete().eq("document_id", document_id).execute()
    
    # Create new relationships
    create_document_units(document_id, unit_ids)


# -----------------------------------------------------
# NEW — Update document_contractors junction table (replace all)
# -----------------------------------------------------
def update_document_contractors(document_id: str, contractor_ids: list):
    client = get_supabase_client()
    
    # Delete existing relationships
    client.table("document_contractors").delete().eq("document_id", document_id).execute()
    
    # Create new relationships
    create_document_contractors(document_id, contractor_ids)


# -----------------------------------------------------
# NEW — Fetch units for a document
# -----------------------------------------------------
def get_document_units(document_id: str) -> list:
    client = get_supabase_client()
    
    # Join document_units with units table
    result = (
        client.table("document_units")
        .select("unit_id, units(*)")
        .eq("document_id", document_id)
        .execute()
    )
    
    units = []
    if result.data:
        for row in result.data:
            if row.get("units"):
                units.append(row["units"])
    
    return units


# -----------------------------------------------------
# NEW — Fetch contractors for a document
# -----------------------------------------------------
def get_document_contractors(document_id: str) -> list:
    client = get_supabase_client()
    
    # Join document_contractors with contractors table
    result = (
        client.table("document_contractors")
        .select("contractor_id, contractors(*)")
        .eq("document_id", document_id)
        .execute()
    )
    
    contractors = []
    if result.data:
        for row in result.data:
            if row.get("contractors"):
                contractor = row["contractors"]
                # Enrich contractor with roles
                contractor = enrich_contractor_with_roles(contractor)
                contractors.append(contractor)
    
    return contractors


# -----------------------------------------------------
# Helper — Enrich contractor with roles
# -----------------------------------------------------
def enrich_contractor_with_roles(contractor: dict) -> dict:
    """Add roles array to contractor dict."""
    contractor_id = contractor.get("id")
    if not contractor_id:
        contractor["roles"] = []
        return contractor
    
    client = get_supabase_client()
    
    # Get roles for this contractor
    role_result = (
        client.table("contractor_role_assignments")
        .select("role_id, contractor_roles(name)")
        .eq("contractor_id", contractor_id)
        .execute()
    )
    
    roles = []
    if role_result.data:
        for row in role_result.data:
            if row.get("contractor_roles") and row["contractor_roles"].get("name"):
                roles.append(row["contractor_roles"]["name"])
    
    contractor["roles"] = roles
    return contractor


# -----------------------------------------------------
# NEW — Enrich document with units and contractors
# -----------------------------------------------------
def enrich_document_with_relations(document: dict) -> dict:
    """Add units and contractors arrays to document dict"""
    document_id = document.get("id")
    if not document_id:
        return document
    
    document["units"] = get_document_units(document_id)
    document["contractors"] = get_document_contractors(document_id)
    
    # Also add unit_ids and contractor_ids for convenience
    document["unit_ids"] = [u["id"] for u in document["units"]]
    document["contractor_ids"] = [c["id"] for c in document["contractors"]]
    
    return document


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
    
    # Note: unit_id filtering is now done via document_units junction table
    # For now, we'll filter in memory after fetching (or use a join query)
    # TODO: Implement proper junction table filtering if needed

    res = query.order("created_at", desc=True).limit(limit).execute()
    documents = res.data or []
    
    # Enrich each document with units and contractors
    enriched_documents = [enrich_document_with_relations(doc) for doc in documents]
    
    return enriched_documents


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
    
    # Validate building_id is not None (required by schema)
    if not building_id:
        raise HTTPException(400, "building_id is required and cannot be null")
    
    # Validate building exists
    client = get_supabase_client()
    building_rows = (
        client.table("buildings")
        .select("id")
        .eq("id", str(building_id))
        .execute()
    ).data
    if not building_rows:
        raise HTTPException(400, f"Building {building_id} does not exist")
    
    # Get unit_ids and contractor_ids from payload
    unit_ids = [str(u) for u in (payload.unit_ids or [])]
    contractor_ids = [str(c) for c in (payload.contractor_ids or [])]
    
    # Check for duplicates
    if len(unit_ids) != len(set(unit_ids)):
        raise HTTPException(400, "Duplicate unit IDs are not allowed")
    if len(contractor_ids) != len(set(contractor_ids)):
        raise HTTPException(400, "Duplicate contractor IDs are not allowed")
    
    # Validate contractors exist
    if contractor_ids:
        client = get_supabase_client()
        for cid in contractor_ids:
            contractor_rows = (
                client.table("contractors")
                .select("id")
                .eq("id", cid)
                .execute()
            ).data
            if not contractor_rows:
                raise HTTPException(400, f"Contractor {cid} does not exist")

    # -------------------------------------------------
    # Determine building based on payload
    # -------------------------------------------------
    if event_id:
        # event defines building
        building_id, _ = get_event_info(event_id)
        building_id = str(building_id)

    elif unit_ids:
        # derive building from first unit
        building_id = get_unit_building(unit_ids[0])
        # Validate all units belong to same building
        validate_units_in_building(unit_ids, building_id)

    elif building_id:
        # OK: building only
        building_id = str(building_id)

    else:
        raise HTTPException(400, "Must provide event_id OR unit_ids OR building_id.")

    # -------------------------------------------------
    # Access Control
    # -------------------------------------------------
    if current_user.role not in ["admin", "super_admin", "hoa"]:
        verify_user_building_access(current_user.id, building_id)

    # -------------------------------------------------
    # Prepare record (exclude unit_ids and contractor_ids - they go to junction tables)
    # -------------------------------------------------
    doc_data = sanitize(payload.model_dump(exclude={"unit_ids", "contractor_ids"}))
    
    doc_data["building_id"] = str(building_id)
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

    # Create junction table entries for units
    create_document_units(doc_id, unit_ids)
    
    # Create junction table entries for contractors
    create_document_contractors(doc_id, contractor_ids)

    fetch_res = (
        client.table("documents")
        .select("*")
        .eq("id", doc_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Created document not found")

    document = fetch_res.data[0]
    
    # Enrich with units and contractors
    document = enrich_document_with_relations(document)

    return document


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

    # Get current document to determine building_id for validation
    current_doc = (
        client.table("documents")
        .select("building_id")
        .eq("id", document_id)
        .limit(1)
        .execute()
    ).data
    
    if not current_doc:
        raise HTTPException(404, "Document not found")
    
    building_id = current_doc[0]["building_id"]
    
    # Handle unit_ids update
    unit_ids = None
    if payload.unit_ids is not None:
        unit_ids = [str(u) for u in payload.unit_ids]
        if unit_ids:
            validate_units_in_building(unit_ids, building_id)
    
    # Handle contractor_ids update
    contractor_ids = None
    if payload.contractor_ids is not None:
        contractor_ids = [str(c) for c in payload.contractor_ids]
        if contractor_ids:
            # Check for duplicates
            if len(contractor_ids) != len(set(contractor_ids)):
                raise HTTPException(400, "Duplicate contractor IDs are not allowed")
            
            # Validate contractors exist
            client = get_supabase_client()
            for cid in contractor_ids:
                contractor_rows = (
                    client.table("contractors")
                    .select("id")
                    .eq("id", cid)
                    .execute()
                ).data
                if not contractor_rows:
                    raise HTTPException(400, f"Contractor {cid} does not exist")

    # Prepare update data (exclude junction table fields)
    update_data = sanitize(payload.model_dump(exclude_unset=True, exclude={"unit_ids", "contractor_ids"}))

    # event_id changed → derive new building
    if "event_id" in update_data and update_data["event_id"]:
        building_id, _ = get_event_info(update_data["event_id"])
        update_data["building_id"] = str(building_id)

    # building only changed → allow (rare)
    if "building_id" in update_data:
        update_data["building_id"] = str(update_data["building_id"])
        building_id = update_data["building_id"]

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

    # Update junction tables if provided
    if unit_ids is not None:
        update_document_units(document_id, unit_ids)
    
    if contractor_ids is not None:
        update_document_contractors(document_id, contractor_ids)

    # Step 2 — Fetch updated
    fetch_res = (
        client.table("documents")
        .select("*")
        .eq("id", document_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Updated document not found")

    document = fetch_res.data[0]
    
    # Enrich with units and contractors
    document = enrich_document_with_relations(document)

    return document


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
