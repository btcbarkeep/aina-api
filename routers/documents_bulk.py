# routers/documents_bulk.py

import uuid
import tempfile
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from typing import Optional

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
from core.utils import sanitize
from core.permission_helpers import require_building_access, is_admin
from core.logging_config import logger

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


# ----------------------------------------
# BULK UPLOAD ENDPOINT
# ----------------------------------------
@router.post(
    "/bulk-upload",
    summary="Bulk upload multiple documents via Excel/PDF list",
    dependencies=[Depends(requires_permission("documents:write"))],
)
async def bulk_upload_documents(
    file: UploadFile = File(...),
    building_id: Optional[str] = Form(None, description="Optional building ID to assign to all documents in the bulk upload. If provided, building_id column in spreadsheet is optional."),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Accepts an Excel file (.xlsx) or CSV containing document metadata.
    Creates 1 row in `documents` per row in the spreadsheet.
    
    If `building_id` is provided as a parameter, all documents will be assigned to that building.
    If not provided, each row must include a `building_id` column.
    """

    # ------------------------------
    # Validate extension
    # ------------------------------
    filename = file.filename.lower()
    if not (filename.endswith(".xlsx") or filename.endswith(".csv")):
        raise HTTPException(400, "File must be .xlsx or .csv")

    # ------------------------------
    # Read file into pandas
    # ------------------------------
    try:
        contents = await file.read()
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(contents)
            tmp.flush()

            if filename.endswith(".xlsx"):
                df = pd.read_excel(tmp.name)
            else:
                df = pd.read_csv(tmp.name)

    except Exception as e:
        raise HTTPException(400, f"Failed to read spreadsheet: {e}")

    if df.empty:
        raise HTTPException(400, "Spreadsheet is empty.")

    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]

    client = get_supabase_client()
    
    # Validate building_id parameter if provided
    global_building_id = None
    if building_id:
        building_id_str = str(building_id).strip()
        try:
            building_check = (
                client.table("buildings")
                .select("id")
                .eq("id", building_id_str)
                .limit(1)
                .execute()
            )
            if not building_check.data:
                raise HTTPException(400, f"Building {building_id_str} does not exist")
            
            # Check user has access to building
            if not is_admin(current_user):
                try:
                    require_building_access(current_user, building_id_str)
                except HTTPException:
                    raise HTTPException(403, f"You do not have access to building {building_id_str}")
            
            global_building_id = building_id_str
            logger.info(f"Bulk upload: Using global building_id {global_building_id} for all documents")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Error validating building_id parameter: {e}")
    
    # Determine required columns based on whether building_id is provided
    required_columns = {"title", "document_url"}
    if not global_building_id:
        required_columns.add("building_id")
    
    missing = required_columns - set(df.columns)
    if missing:
        raise HTTPException(400, f"Missing required columns: {', '.join(missing)}")

    created_docs = []

    # ------------------------------
    # Loop through all rows and insert with validation
    # ------------------------------
    errors = []
    for idx, row in df.iterrows():
        row_num = idx + 2  # +2 because Excel/CSV is 1-indexed and has header
        row = row.to_dict()
        
        # Use global building_id if provided, otherwise use row's building_id
        row_building_id = row.get("building_id")
        if global_building_id:
            # Use global building_id for all documents (ignore row-level building_id if present)
            building_id_str = global_building_id
        else:
            # Use row-level building_id (required if global not provided)
            if not row_building_id:
                errors.append(f"Row {row_num}: building_id is required (either as parameter or in spreadsheet)")
                continue
            
            building_id_str = str(row_building_id)
            
            # Validate row-level building_id exists
            try:
                building_check = (
                    client.table("buildings")
                    .select("id")
                    .eq("id", building_id_str)
                    .limit(1)
                    .execute()
                )
                if not building_check.data:
                    errors.append(f"Row {row_num}: Building {building_id_str} does not exist")
                    continue
                
                # Check user has access to building
                if not is_admin(current_user):
                    try:
                        require_building_access(current_user, building_id_str)
                    except HTTPException:
                        errors.append(f"Row {row_num}: You do not have access to building {building_id_str}")
                        continue
            except Exception as e:
                errors.append(f"Row {row_num}: Error validating building: {e}")
                continue
        
        unit_id = row.get("unit_id")
        event_id = row.get("event_id")
        
        # Validate unit_id exists and belongs to building
        if unit_id and building_id_str:
            unit_id_str = str(unit_id)
            try:
                unit_check = (
                    client.table("units")
                    .select("id, building_id")
                    .eq("id", unit_id_str)
                    .limit(1)
                    .execute()
                )
                if not unit_check.data:
                    errors.append(f"Row {row_num}: Unit {unit_id_str} does not exist")
                    continue
                unit_building_id = unit_check.data[0].get("building_id")
                if unit_building_id and str(unit_building_id) != building_id_str:
                    errors.append(f"Row {row_num}: Unit {unit_id_str} does not belong to building {building_id_str}")
                    continue
            except Exception as e:
                errors.append(f"Row {row_num}: Error validating unit: {e}")
                continue
        
        # Validate event_id exists
        if event_id:
            event_id_str = str(event_id)
            try:
                event_check = (
                    client.table("events")
                    .select("id")
                    .eq("id", event_id_str)
                    .limit(1)
                    .execute()
                )
                if not event_check.data:
                    errors.append(f"Row {row_num}: Event {event_id_str} does not exist")
                    continue
            except Exception as e:
                errors.append(f"Row {row_num}: Error validating event: {e}")
                continue
        
        # Public documents category UUID for bulk uploads - validate it exists
        PUBLIC_DOCUMENTS_CATEGORY_ID = "f5ae850f-cc31-44ff-b5bc-ee7d708a0c31"
        try:
            category_check = (
                client.table("document_categories")
                .select("id")
                .eq("id", PUBLIC_DOCUMENTS_CATEGORY_ID)
                .limit(1)
                .execute()
            )
            if not category_check.data:
                errors.append(f"Row {row_num}: Public documents category {PUBLIC_DOCUMENTS_CATEGORY_ID} not found in document_categories table")
                continue
        except Exception as e:
            errors.append(f"Row {row_num}: Error validating public documents category: {e}")
            continue
        
        doc_data = {
            "id": str(uuid.uuid4()),
            "title": row.get("title"),
            "document_url": row.get("document_url"),
            "building_id": building_id_str,  # Always set since we validated it exists
            "unit_id": str(unit_id) if unit_id else None,
            "event_id": str(event_id) if event_id else None,
            "category_id": PUBLIC_DOCUMENTS_CATEGORY_ID,  # All bulk uploads use public_documents category
            "permit_number": row.get("permit_number"),
            "permit_type": row.get("permit_type"),
            "folder": row.get("folder"),
            "tmk": row.get("tmk"),
            "description": row.get("description"),
            "uploaded_by": str(current_user.id),
        }

        sanitized = sanitize(doc_data)

        try:
            res = client.table("documents").insert(sanitized).execute()
            if res.data:
                created_docs.append(res.data[0])
            else:
                errors.append(f"Row {row_num}: Insert returned no data")
        except Exception as e:
            error_msg = str(e)
            if "foreign key" in error_msg.lower() or "violates foreign key" in error_msg.lower():
                errors.append(f"Row {row_num}: Invalid reference (building_id, unit_id, or event_id)")
            elif "duplicate" in error_msg.lower():
                errors.append(f"Row {row_num}: Duplicate entry")
            else:
                errors.append(f"Row {row_num}: Insert failed: {error_msg}")
            logger.warning(f"Bulk upload error on row {row_num}: {e}")

    if errors:
        return {
            "status": "partial_success",
            "count": len(created_docs),
            "errors": errors,
            "documents": created_docs,
        }

    return {
        "status": "success",
        "count": len(created_docs),
        "documents": created_docs,
    }
