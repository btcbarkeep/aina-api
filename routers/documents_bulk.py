# routers/documents_bulk.py

import uuid
import tempfile
import re
import pandas as pd
import numpy as np
from urllib.parse import urlparse, unquote, parse_qs
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
    source: Optional[str] = Form(None, description="Optional source text to apply to all documents in the bulk upload (e.g., 'Maui County Permits', 'Public Records', etc.)"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Accepts an Excel file (.xlsx) or CSV containing document metadata.
    Creates 1 row in `documents` per row in the spreadsheet.
    
    - If `building_id` is provided as a parameter, all documents will be assigned to that building.
    - If `source` is provided, it will be applied to all documents.
    - All bulk upload documents are automatically set to `is_public=True`.
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

    # Store original column names for debugging
    original_columns = list(df.columns)
    logger.info(f"Bulk upload: Original columns in spreadsheet: {original_columns}")

    # Normalize column names (lowercase, strip whitespace, replace spaces with underscores)
    # Also handle common variations and remove special characters
    normalized_columns = []
    for col in df.columns:
        # Convert to string, strip, lowercase
        col_str = str(col).strip().lower()
        # Replace multiple spaces with single space, then replace spaces with underscores
        col_str = re.sub(r'\s+', ' ', col_str).replace(" ", "_")
        # Remove any remaining special characters except underscores and alphanumeric
        col_str = re.sub(r'[^a-z0-9_]', '', col_str)
        normalized_columns.append(col_str)
    
    df.columns = normalized_columns
    logger.info(f"Bulk upload: Normalized columns: {normalized_columns}")
    
    # Map alternative column names to standard names
    column_mapping = {}
    
    # Map document_url alternatives (after normalization, "document url" becomes "document_url", "document link" becomes "document_link", "download link" becomes "download_link")
    document_url_alternatives = ["document_url", "document_link", "download_link", "download_url"]
    for col in normalized_columns:
        if col in document_url_alternatives:
            column_mapping[col] = "document_url"
            logger.info(f"Bulk upload: Mapped column '{col}' to 'document_url'")
            break
    
    # Map permit_number alternatives (after normalization, "permit number" becomes "permit_number", "PERMITNUMBER" becomes "permitnumber")
    permit_number_alternatives = ["permit_number", "permitnumber"]
    for col in normalized_columns:
        if col in permit_number_alternatives:
            column_mapping[col] = "permit_number"
            logger.info(f"Bulk upload: Mapped column '{col}' to 'permit_number'")
            break
    
    # Map permit_type alternatives (after normalization, "permit type" becomes "permit_type", "PERMITTYPE" becomes "permittype")
    permit_type_alternatives = ["permit_type", "permittype"]
    for col in normalized_columns:
        if col in permit_type_alternatives:
            column_mapping[col] = "permit_type"
            logger.info(f"Bulk upload: Mapped column '{col}' to 'permit_type'")
            break
    
    # Map tmk alternatives (after normalization, "TMK" becomes "tmk")
    tmk_alternatives = ["tmk"]
    for col in normalized_columns:
        if col in tmk_alternatives:
            column_mapping[col] = "tmk"
            logger.info(f"Bulk upload: Mapped column '{col}' to 'tmk'")
            break
    
    # Note: We don't map title/project_name/description to filename here
    # Instead, we check for them in priority order when reading each row
    
    # Rename columns using the mapping
    if column_mapping:
        df = df.rename(columns=column_mapping)
        logger.info(f"Bulk upload: Columns after mapping: {list(df.columns)}")

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
    # filename can come from "title", "project_name", or "description" columns
    required_columns = {"document_url"}
    if not global_building_id:
        required_columns.add("building_id")
    
    # Check if at least one filename source column exists
    filename_sources = ["title", "project_name", "description"]
    has_filename_source = any(col in df.columns for col in filename_sources)
    
    if not has_filename_source:
        found_columns = sorted(list(df.columns))
        raise HTTPException(
            400, 
            f"Missing filename source column. Need one of: title, project_name (or 'Project Name'), or description. "
            f"Found columns in spreadsheet: {', '.join(found_columns)}"
        )
    
    missing = required_columns - set(df.columns)
    if missing:
        # Provide helpful error message with accepted alternatives and show found columns
        error_msg = "Missing required columns: "
        missing_list = []
        for col in missing:
            if col == "document_url":
                missing_list.append("document_url (or 'document url', 'document link', 'document_link', 'download link', 'download_link', 'download url', 'download_url')")
            else:
                missing_list.append(col)
        
        # Include found columns in error message for debugging
        found_columns = sorted(list(df.columns))
        error_msg += ", ".join(missing_list)
        error_msg += f". Found columns in spreadsheet: {', '.join(found_columns)}"
        raise HTTPException(400, error_msg)

    created_docs = []

    # ------------------------------
    # Loop through all rows and insert with validation
    # ------------------------------
    errors = []
    for idx, row in df.iterrows():
        row_num = idx + 2  # +2 because Excel/CSV is 1-indexed and has header
        # Convert row to dict and handle pandas types
        row_dict = {}
        for col in row.index:
            value = row[col]
            # Convert pandas types immediately
            if pd.isna(value):
                row_dict[col] = None
            elif isinstance(value, (np.integer, np.int64, np.int32)):
                row_dict[col] = int(value)
            elif isinstance(value, (np.floating, np.float64, np.float32)):
                row_dict[col] = float(value)
            elif isinstance(value, np.bool_):
                row_dict[col] = bool(value)
            elif isinstance(value, pd.Timestamp):
                row_dict[col] = None
            elif value is pd.NaT:  # Check for NaT (Not a Time) using identity check
                row_dict[col] = None
            else:
                row_dict[col] = value
        row = row_dict
        
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
        
        # Helper function to convert pandas types to Python native types
        def clean_value(value):
            """Convert pandas NaN/NaT to None, and ensure native Python types."""
            # Handle None and pandas NaN/NaT
            if value is None or pd.isna(value):
                return None
            
            # Handle numpy types
            if isinstance(value, (np.integer, np.int64, np.int32)):
                return int(value)
            if isinstance(value, (np.floating, np.float64, np.float32)):
                return float(value)
            if isinstance(value, np.bool_):
                return bool(value)
            
            # Handle pandas timestamp types
            if isinstance(value, pd.Timestamp):
                return None
            if value is pd.NaT:  # Check for NaT (Not a Time) using identity check
                return None
            
            # Handle strings - strip and return None if empty
            if isinstance(value, str):
                cleaned = value.strip()
                return cleaned if cleaned else None
            
            # For any other type, convert to string
            try:
                str_value = str(value).strip()
                return str_value if str_value else None
            except Exception:
                return None
        
        # Get filename from spreadsheet - check title, project_name, or description in that order
        filename = None
        filename_sources = ["title", "project_name", "description"]
        for source_col in filename_sources:
            value = clean_value(row.get(source_col))
            if value:
                filename = value
                logger.debug(f"Row {row_num}: Using '{source_col}' column for filename: {filename}")
                break
        
        document_url = clean_value(row.get("document_url"))
        
        # If filename not provided from any source, try to extract from URL or use fallback
        if not filename:
            if document_url:
                try:
                    parsed_url = urlparse(document_url)
                    # Try to get filename from URL path
                    path = unquote(parsed_url.path)
                    if path and '/' in path:
                        filename = path.split('/')[-1]
                        # Remove query parameters if any
                        if '?' in filename:
                            filename = filename.split('?')[0]
                        # Clean up the filename
                        if filename:
                            filename = filename.strip()
                    # If no filename in path, try to get from query params (common in some systems)
                    if not filename or filename == '':
                        query_params = parse_qs(parsed_url.query)
                        # Check common filename parameters
                        for param in ['f', 'file', 'filename', 'name']:
                            if param in query_params and query_params[param]:
                                filename = query_params[param][0].strip()
                                break
                except Exception as e:
                    logger.warning(f"Row {row_num}: Error extracting filename from URL: {e}")
            
            # Final fallback
            if not filename:
                filename = "bulk_upload_document.pdf"
        
        doc_data = {
            "id": str(uuid.uuid4()),
            "filename": filename,  # From "title", "project_name", or "description" column in spreadsheet
            "document_url": document_url,
            "building_id": building_id_str,  # Always set since we validated it exists
            "unit_id": str(unit_id) if unit_id else None,
            "event_id": str(event_id) if event_id else None,
            "category_id": PUBLIC_DOCUMENTS_CATEGORY_ID,  # All bulk uploads use public_documents category
            "permit_number": clean_value(row.get("permit_number")),
            "permit_type": clean_value(row.get("permit_type")),
            "folder": clean_value(row.get("folder")),
            "tmk": clean_value(row.get("tmk")),
            "description": clean_value(row.get("description")),
            "source": source if source else None,  # Apply source to all documents if provided
            "is_public": True,  # All bulk upload documents are public
            "uploaded_by": str(current_user.id),
        }

        sanitized = sanitize(doc_data)
        
        # Remove any None values that might cause issues, but keep empty strings as None
        # PostgREST doesn't like certain None values in some contexts
        # Keep optional fields that can be None: unit_id, event_id, source
        final_data = {k: v for k, v in sanitized.items() if v is not None or k in ["unit_id", "event_id", "source"]}
        
        # Log the data being sent for debugging (first few rows only)
        if row_num <= 5:
            logger.info(f"Bulk upload row {row_num} data: {final_data}")

        try:
            res = client.table("documents").insert(final_data).execute()
            if res.data:
                created_docs.append(res.data[0])
            else:
                errors.append(f"Row {row_num}: Insert returned no data")
        except Exception as e:
            error_msg = str(e)
            # Log the actual data that failed for debugging
            logger.error(f"Bulk upload error on row {row_num}: {e}. Data: {final_data}")
            if "foreign key" in error_msg.lower() or "violates foreign key" in error_msg.lower():
                errors.append(f"Row {row_num}: Invalid reference (building_id, unit_id, or event_id)")
            elif "duplicate" in error_msg.lower():
                errors.append(f"Row {row_num}: Duplicate entry")
            elif "empty or invalid json" in error_msg.lower() or "pgrst102" in error_msg.lower():
                errors.append(f"Row {row_num}: Invalid data format - check for empty or malformed values")
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
