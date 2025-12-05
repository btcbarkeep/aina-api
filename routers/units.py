# routers/units.py

from fastapi import (
    APIRouter, HTTPException, UploadFile, File, Form, Depends
)
from typing import Optional
import csv
import io

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client
from core.logging_config import logger
from core.permission_helpers import (
    is_admin,
    require_unit_access as require_unit_access_helper,
    require_building_access,
    get_user_accessible_unit_ids,
)
from models.unit import UnitCreate, UnitUpdate


router = APIRouter(
    prefix="/units",
    tags=["Units"],
)

FULL_ACCESS_ROLES = ["admin", "super_admin", "aoao"]


# -------------------------------------------------------------
# Permission check (legacy - kept for backward compatibility)
# -------------------------------------------------------------
def require_unit_access(user: CurrentUser):
    """Legacy function - checks if user can manage units (admin/aoao only)."""
    if user.role not in FULL_ACCESS_ROLES:
        raise HTTPException(403, "You do not have permission to manage units.")


# -------------------------------------------------------------
# Normalize blank → None
# -------------------------------------------------------------
def clean(value):
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


# -------------------------------------------------------------
# Convert string to int (for numeric fields that might come as strings)
# -------------------------------------------------------------
def to_int_or_none(value):
    """Convert value to int if possible, otherwise return None."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
        try:
            # Try to convert to int (handles "6", "6.0", etc.)
            return int(float(value))
        except (ValueError, TypeError):
            return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


# -------------------------------------------------------------
# Convert string to numeric/decimal (for numeric fields that might come as strings)
# -------------------------------------------------------------
def to_numeric_or_none(value):
    """Convert value to numeric (decimal) if possible, otherwise return None."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "" or value.lower() == "string":  # Skip placeholder values
            return None
        try:
            # Convert to float (numeric type in database)
            return float(value)
        except (ValueError, TypeError):
            return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


# -------------------------------------------------------------
# LIST Units for a Building
# -------------------------------------------------------------
@router.get("/building/{building_id}")
def list_units(building_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # Permission check: ensure user has access to this building
    if not is_admin(current_user):
        require_building_access(current_user, building_id)

    client = get_supabase_client()

    try:
        query = (
            client.table("units")
            .select("*")
            .eq("building_id", building_id)
        )
        
        # For non-admin users, filter to only units they have access to
        if not is_admin(current_user):
            accessible_unit_ids = get_user_accessible_unit_ids(current_user)
            if accessible_unit_ids is not None:
                query = query.in_("id", accessible_unit_ids)
        
        result = query.order("unit_number").execute()
        return result.data or []
    except Exception as e:
        raise HTTPException(500, f"Unable to fetch units: {e}")


# -------------------------------------------------------------
# CREATE Unit
# -------------------------------------------------------------
@router.post("")
def create_unit(payload: UnitCreate, current_user: CurrentUser = Depends(get_current_user)):
    require_unit_access(current_user)

    client = get_supabase_client()
    # Convert Pydantic model to dict, cleaning and converting types
    data = payload.model_dump()
    cleaned = {}
    
    for k, v in data.items():
        if v is None:
            continue
        # Convert integer fields that might come as strings
        if k in ["bedrooms", "bathrooms", "square_feet"]:
            converted = to_int_or_none(v)
            if converted is not None:
                cleaned[k] = converted
            else:
                # Log if conversion failed for debugging
                logger.warning(f"Failed to convert {k}={v} (type: {type(v)}) to integer, skipping field")
        # Convert numeric (decimal) fields that might come as strings
        elif k == "parcel_number":
            converted = to_numeric_or_none(v)
            if converted is not None:
                cleaned[k] = converted
            else:
                logger.warning(f"Failed to convert {k}={v} (type: {type(v)}) to numeric, skipping field")
        # floor is text type, so keep as string (but clean it)
        else:
            cleaned_value = clean(v)
            # Skip placeholder "string" values (common in API testing)
            if cleaned_value == "string":
                logger.warning(f"Skipping placeholder value 'string' for field {k}")
                continue
            if cleaned_value is not None:
                cleaned[k] = cleaned_value
    
    logger.info(f"Creating unit - original data: {data}")
    logger.info(f"Creating unit with cleaned data: {cleaned}")

    try:
        result = (
            client.table("units")
            .insert(cleaned, returning="representation")
            .execute()
        )
        if not result.data:
            raise HTTPException(500, "Unit creation failed - no data returned")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Unit creation failed: {e}")


# -------------------------------------------------------------
# UPDATE Unit
# -------------------------------------------------------------
@router.patch("/{unit_id}")
def update_unit(unit_id: str, payload: UnitUpdate, current_user: CurrentUser = Depends(get_current_user)):
    require_unit_access(current_user)

    client = get_supabase_client()
    # Convert Pydantic model to dict, excluding None values for partial updates
    data = payload.model_dump(exclude_unset=True)
    cleaned = {}
    
    for k, v in data.items():
        if v is None:
            continue
        # Convert integer fields that might come as strings
        if k in ["bedrooms", "bathrooms", "square_feet"]:
            converted = to_int_or_none(v)
            if converted is not None:
                cleaned[k] = converted
        # Convert numeric (decimal) fields that might come as strings
        elif k == "parcel_number":
            converted = to_numeric_or_none(v)
            if converted is not None:
                cleaned[k] = converted
        # floor is text type, so keep as string (but clean it)
        else:
            cleaned_value = clean(v)
            # Skip placeholder "string" values (common in API testing)
            if cleaned_value == "string":
                logger.warning(f"Skipping placeholder value 'string' for field {k}")
                continue
            if cleaned_value is not None:
                cleaned[k] = cleaned_value

    try:
        result = (
            client.table("units")
            .update(cleaned, returning="representation")
            .eq("id", unit_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(404, f"Unit {unit_id} not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Unit update failed: {e}")


# -------------------------------------------------------------
# DELETE Unit
# -------------------------------------------------------------
@router.delete("/{unit_id}")
def delete_unit(unit_id: str, current_user: CurrentUser = Depends(get_current_user)):
    require_unit_access(current_user)

    client = get_supabase_client()

    try:
        client.table("units").delete().eq("id", unit_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Unit deletion failed: {e}")


# -------------------------------------------------------------
# GET Single Unit
# -------------------------------------------------------------
@router.get("/{unit_id}")
def get_unit(unit_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # Permission check: ensure user has access to this unit
    if not is_admin(current_user):
        require_unit_access_helper(current_user, unit_id)

    client = get_supabase_client()
    try:
        result = (
            client.table("units")
            .select("*")
            .eq("id", unit_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(404, f"Unit {unit_id} not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Unable to fetch unit: {e}")


# -------------------------------------------------------------
# BULK UPLOAD Units (CSV)
# -------------------------------------------------------------
@router.post("/bulk-upload")
def bulk_upload_units(
    building_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    require_unit_access(current_user)

    client = get_supabase_client()

    try:
        content = file.file.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
    except Exception:
        raise HTTPException(400, "Invalid CSV file.")

    required_fields = ["unit_number"]
    rows_to_insert = []

    for i, row in enumerate(reader, start=1):

        for f in required_fields:
            if not row.get(f):
                raise HTTPException(400, f"Row {i}: Missing required field '{f}'")

        def to_int(val):
            if val in ("", None):
                return None
            try:
                return int(val)
            except:
                raise HTTPException(400, f"Row {i}: Invalid integer '{val}'")

        rows_to_insert.append({
            "building_id": building_id,
            "unit_number": clean(row.get("unit_number")),
            "floor": clean(row.get("floor")),
            "bedrooms": to_int(row.get("bedrooms")),
            "bathrooms": to_int(row.get("bathrooms")),
            "square_feet": to_int(row.get("square_feet")),
            "owner_name": clean(row.get("owner_name")),
            "parcel_number": clean(row.get("parcel_number")),
        })

    try:
        client.table("units").insert(rows_to_insert).execute()
    except Exception as e:
        raise HTTPException(500, f"Bulk upload failed: {e}")

    return {"success": True, "inserted": len(rows_to_insert)}


# -------------------------------------------------------------
# LIST Unit Events
# -------------------------------------------------------------
@router.get("/{unit_id}/events")
def list_unit_events(unit_id: str, current_user: CurrentUser = Depends(get_current_user)):
    require_unit_access(current_user)

    client = get_supabase_client()

    try:
        result = (
            client.table("events")
            .select("*")
            .eq("unit_id", unit_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        raise HTTPException(500, f"Unable to fetch unit events: {e}")


# -------------------------------------------------------------
# LIST Unit Documents
# -------------------------------------------------------------
@router.get("/{unit_id}/documents")
def list_unit_documents(unit_id: str, current_user: CurrentUser = Depends(get_current_user)):
    require_unit_access(current_user)

    client = get_supabase_client()

    try:
        result = (
            client.table("documents")
            .select("*")
            .eq("unit_id", unit_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        raise HTTPException(500, f"Unable to fetch unit documents: {e}")
