# routers/documents.py

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List, Dict
from datetime import datetime

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
from core.utils import sanitize
from core.permission_helpers import (
    is_admin,
    require_building_access,
    require_units_access,
    require_document_access,
    get_user_accessible_unit_ids,
    get_user_accessible_building_ids,
)
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
            error_msg = str(e).lower()
            if "duplicate" in error_msg or "unique" in error_msg:
                # Expected: duplicate key errors are okay (idempotent operation)
                logger.debug(f"Duplicate document_unit relationship ignored: document_id={document_id}, unit_id={unit_id}")
            else:
                logger.warning(f"Failed to create document_unit relationship: {e}")
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
            error_msg = str(e).lower()
            if "duplicate" in error_msg or "unique" in error_msg:
                # Expected: duplicate key errors are okay (idempotent operation)
                logger.debug(f"Duplicate document_contractor relationship ignored: document_id={document_id}, contractor_id={contractor_id}")
            else:
                logger.warning(f"Failed to create document_contractor relationship: {e}")
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
# Helper — Enrich contractor with roles (centralized)
# -----------------------------------------------------
from core.contractor_helpers import enrich_contractor_with_roles


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
# Helper — Apply document filters
# -----------------------------------------------------
def apply_document_filters(query, params: dict):
    """Apply filtering to documents query based on provided parameters."""
    client = get_supabase_client()
    
    # building_id filter
    if params.get("building_id"):
        query = query.eq("building_id", params["building_id"])
    
    # event_id filter
    if params.get("event_id"):
        query = query.eq("event_id", params["event_id"])
    
    # category_id filter
    if params.get("category_id"):
        query = query.eq("category_id", params["category_id"])
    
    # subcategory_id filter
    if params.get("subcategory_id"):
        query = query.eq("subcategory_id", params["subcategory_id"])
    
    # uploaded_by filter
    if params.get("uploaded_by"):
        query = query.eq("uploaded_by", params["uploaded_by"])
    
    # date range filters (using created_at)
    if params.get("start_date"):
        query = query.gte("created_at", params["start_date"])
    if params.get("end_date"):
        query = query.lte("created_at", params["end_date"])
    
    # unit_id filter (via document_units junction table)
    if params.get("unit_id"):
        # Get document IDs that have this unit
        document_units_result = (
            client.table("document_units")
            .select("document_id")
            .eq("unit_id", params["unit_id"])
            .execute()
        )
        document_ids = [row["document_id"] for row in (document_units_result.data or [])]
        if document_ids:
            query = query.in_("id", document_ids)
        else:
            # No documents match, return empty result
            query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
    
    # unit_ids filter (via document_units junction table)
    if params.get("unit_ids"):
        unit_ids = params["unit_ids"]
        if unit_ids:
            # Get document IDs that have ANY of these units
            document_units_result = (
                client.table("document_units")
                .select("document_id")
                .in_("unit_id", unit_ids)
                .execute()
            )
            document_ids = list(set([row["document_id"] for row in (document_units_result.data or [])]))
            if document_ids:
                query = query.in_("id", document_ids)
            else:
                # No documents match, return empty result
                query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
    
    # contractor_id filter (via document_contractors junction table)
    if params.get("contractor_id"):
        # Get document IDs that have this contractor
        document_contractors_result = (
            client.table("document_contractors")
            .select("document_id")
            .eq("contractor_id", params["contractor_id"])
            .execute()
        )
        document_ids = [row["document_id"] for row in (document_contractors_result.data or [])]
        if document_ids:
            query = query.in_("id", document_ids)
        else:
            # No documents match, return empty result
            query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
    
    # contractor_ids filter (via document_contractors junction table)
    if params.get("contractor_ids"):
        contractor_ids = params["contractor_ids"]
        if contractor_ids:
            # Get document IDs that have ANY of these contractors
            document_contractors_result = (
                client.table("document_contractors")
                .select("document_id")
                .in_("contractor_id", contractor_ids)
                .execute()
            )
            document_ids = list(set([row["document_id"] for row in (document_contractors_result.data or [])]))
            if document_ids:
                query = query.in_("id", document_ids)
            else:
                # No documents match, return empty result
                query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
    
    return query


# -----------------------------------------------------
# LIST DOCUMENTS
# -----------------------------------------------------
@router.get("", summary="List Documents")
def list_documents(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of documents to return (1-1000)"),
    building_id: Optional[str] = Query(None, description="Filter by building ID"),
    event_id: Optional[str] = Query(None, description="Filter by event ID"),
    unit_id: Optional[str] = Query(None, description="Filter by single unit ID"),
    unit_ids: Optional[List[str]] = Query([], description="Filter by list of unit IDs"),
    contractor_id: Optional[str] = Query(None, description="Filter by single contractor ID"),
    contractor_ids: Optional[List[str]] = Query([], description="Filter by list of contractor IDs"),
    category_id: Optional[str] = Query(None, description="Filter by category ID from document_categories table"),
    subcategory_id: Optional[str] = Query(None, description="Filter by subcategory ID from document_subcategories table"),
    uploaded_by: Optional[str] = Query(None, description="Filter by user who uploaded"),
    start_date: Optional[datetime] = Query(None, description="Filter documents from this date (ISO datetime)"),
    end_date: Optional[datetime] = Query(None, description="Filter documents until this date (ISO datetime)"),
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    query = client.table("documents").select("*")
    
    # Apply filters
    filter_params = {
        "building_id": building_id,
        "event_id": event_id,
        "unit_id": unit_id,
        "unit_ids": unit_ids if unit_ids else None,
        "contractor_id": contractor_id,
        "contractor_ids": contractor_ids if contractor_ids else None,
        "category_id": category_id,
        "subcategory_id": subcategory_id,
        "uploaded_by": uploaded_by,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }
    
    query = apply_document_filters(query, filter_params)
    query = query.order("created_at", desc=True).limit(limit)

    res = query.execute()
    documents = res.data or []
    
    # Apply permission-based filtering for non-admin users
    if not is_admin(current_user):
        accessible_unit_ids = get_user_accessible_unit_ids(current_user)
        accessible_building_ids = get_user_accessible_building_ids(current_user)
        
        # Batch fetch all document_units for all documents (prevents N+1 queries)
        document_ids = [d.get("id") for d in documents if d.get("id")]
        document_units_map: Dict[str, List[str]] = {}
        if document_ids:
            document_units_result = (
                client.table("document_units")
                .select("document_id, unit_id")
                .in_("document_id", document_ids)
                .execute()
            )
            if document_units_result.data:
                for row in document_units_result.data:
                    doc_id = row.get("document_id")
                    unit_id = row.get("unit_id")
                    if doc_id and unit_id:
                        if doc_id not in document_units_map:
                            document_units_map[doc_id] = []
                        document_units_map[doc_id].append(unit_id)
        
        filtered_documents = []
        for document in documents:
            document_id = document.get("id")
            document_building_id = document.get("building_id")
            
            # AOAO roles: filter by building access
            if current_user.role in ["aoao", "aoao_staff"]:
                if accessible_building_ids is None or document_building_id in accessible_building_ids:
                    filtered_documents.append(document)
                continue
            
            # Other roles: filter by unit access
            # Get units for this document from pre-fetched map
            document_unit_ids = document_units_map.get(document_id, [])
            
            if not document_unit_ids:
                # Document has no units, check building access
                if accessible_building_ids is None or document_building_id in accessible_building_ids:
                    filtered_documents.append(document)
            else:
                # Check if user has access to any unit in the document
                if accessible_unit_ids is None or any(uid in accessible_unit_ids for uid in document_unit_ids):
                    filtered_documents.append(document)
        
        documents = filtered_documents
    
    # Batch enrich all documents with units and contractors (prevents N+1 queries)
    from core.batch_helpers import batch_enrich_documents_with_relations
    enriched_documents = batch_enrich_documents_with_relations(documents)
    
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
    
    # Batch validate contractors exist (prevents N+1 queries)
    if contractor_ids:
        client = get_supabase_client()
        contractors_result = (
            client.table("contractors")
            .select("id")
            .in_("id", contractor_ids)
            .execute()
        )
        existing_contractor_ids = {row["id"] for row in (contractors_result.data or [])}
        missing_contractors = [cid for cid in contractor_ids if cid not in existing_contractor_ids]
        if missing_contractors:
            raise HTTPException(400, f"Contractors do not exist: {', '.join(missing_contractors)}")
    
    # Validate category_id exists if provided
    if payload.category_id:
        category_result = (
            client.table("document_categories")
            .select("id")
            .eq("id", str(payload.category_id))
            .limit(1)
            .execute()
        )
        if not category_result.data:
            raise HTTPException(400, f"Category ID {payload.category_id} not found in document_categories table")
    
    # Validate subcategory_id exists if provided
    if payload.subcategory_id:
        subcategory_result = (
            client.table("document_subcategories")
            .select("id, category_id")
            .eq("id", str(payload.subcategory_id))
            .limit(1)
            .execute()
        )
        if not subcategory_result.data:
            raise HTTPException(400, f"Subcategory ID {payload.subcategory_id} not found in document_subcategories table")
        # Validate that subcategory belongs to the provided category (if category_id is also provided)
        if payload.category_id and subcategory_result.data[0]["category_id"] != str(payload.category_id):
            raise HTTPException(400, f"Subcategory {payload.subcategory_id} does not belong to category {payload.category_id}")

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
    # Permission checks: ensure user has access to building and all units
    # -------------------------------------------------
    if not is_admin(current_user):
        # Check building access
        require_building_access(current_user, building_id)
        
        # Check unit access (if units provided)
        if unit_ids:
            # AOAO roles can create documents for their building even without unit access
            if current_user.role not in ["aoao", "aoao_staff"]:
                require_units_access(current_user, unit_ids)

    # -------------------------------------------------
    # Prepare record (exclude unit_ids, contractor_ids, and document_url - they go to junction tables or are bulk-only)
    # -------------------------------------------------
    doc_data = sanitize(payload.model_dump(exclude={"unit_ids", "contractor_ids", "document_url"}))
    
    doc_data["building_id"] = str(building_id)
    doc_data["event_id"] = str(event_id) if event_id else None
    doc_data["uploaded_by"] = str(current_user.id)
    
    # Convert UUID objects to strings for Supabase
    if doc_data.get("category_id"):
        doc_data["category_id"] = str(doc_data["category_id"])
    if doc_data.get("subcategory_id"):
        doc_data["subcategory_id"] = str(doc_data["subcategory_id"])

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
def update_document(document_id: str, payload: DocumentUpdate, current_user: CurrentUser = Depends(get_current_user)):
    client = get_supabase_client()

    # Permission check: ensure user has access to this document
    require_document_access(current_user, document_id)

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
            # Permission check for unit_ids if being updated
            if not is_admin(current_user):
                # AOAO roles can update documents for their building even without unit access
                if current_user.role not in ["aoao", "aoao_staff"]:
                    require_units_access(current_user, unit_ids)
    
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
    
    # Validate category_id exists if provided
    if payload.category_id is not None:
        category_result = (
            client.table("document_categories")
            .select("id")
            .eq("id", str(payload.category_id))
            .limit(1)
            .execute()
        )
        if not category_result.data:
            raise HTTPException(400, f"Category ID {payload.category_id} not found in document_categories table")
    
    # Validate subcategory_id exists if provided
    if payload.subcategory_id is not None:
        subcategory_result = (
            client.table("document_subcategories")
            .select("id, category_id")
            .eq("id", str(payload.subcategory_id))
            .limit(1)
            .execute()
        )
        if not subcategory_result.data:
            raise HTTPException(400, f"Subcategory ID {payload.subcategory_id} not found in document_subcategories table")
        # Validate that subcategory belongs to the provided category (if category_id is also provided)
        if payload.category_id is not None and subcategory_result.data[0]["category_id"] != str(payload.category_id):
            raise HTTPException(400, f"Subcategory {payload.subcategory_id} does not belong to category {payload.category_id}")

    # Prepare update data (exclude junction table fields)
    update_data = sanitize(payload.model_dump(exclude_unset=True, exclude={"unit_ids", "contractor_ids", "document_url"}))

    # event_id changed → derive new building
    if "event_id" in update_data and update_data["event_id"]:
        building_id, _ = get_event_info(update_data["event_id"])
        update_data["building_id"] = str(building_id)

    # building only changed → allow (rare)
    if "building_id" in update_data:
        update_data["building_id"] = str(update_data["building_id"])
        building_id = update_data["building_id"]
    
    # Convert UUID objects to strings for Supabase
    if "category_id" in update_data and update_data["category_id"]:
        update_data["category_id"] = str(update_data["category_id"])
    if "subcategory_id" in update_data and update_data["subcategory_id"]:
        update_data["subcategory_id"] = str(update_data["subcategory_id"])

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
