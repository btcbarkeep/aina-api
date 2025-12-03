# routers/units.py

from fastapi import (
    APIRouter, HTTPException, UploadFile, File, Form, Depends
)
from typing import Optional
import csv
import io

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client


router = APIRouter(
    prefix="/units",
    tags=["Units"],
)

FULL_ACCESS_ROLES = ["admin", "super_admin", "aoao"]


# -------------------------------------------------------------
# Permission check
# -------------------------------------------------------------
def require_unit_access(user: CurrentUser):
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
# LIST Units for a Building
# -------------------------------------------------------------
@router.get("/building/{building_id}")
def list_units(building_id: str, current_user: CurrentUser = Depends(get_current_user)):
    require_unit_access(current_user)

    client = get_supabase_client()

    try:
        result = (
            client.table("units")
            .select("*")
            .eq("building_id", building_id)
            .order("unit_number")
            .execute()
        )
        return result.data or []
    except Exception as e:
        raise HTTPException(500, f"Unable to fetch units: {e}")


# -------------------------------------------------------------
# CREATE Unit
# -------------------------------------------------------------
@router.post("")
def create_unit(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    require_unit_access(current_user)

    client = get_supabase_client()
    cleaned = {k: clean(v) for k, v in payload.items()}

    try:
        result = (
            client.table("units")
            .insert(cleaned)
            .select("*")
            .single()
            .execute()
        )
        return result.data
    except Exception as e:
        raise HTTPException(500, f"Unit creation failed: {e}")


# -------------------------------------------------------------
# UPDATE Unit
# -------------------------------------------------------------
@router.patch("/{unit_id}")
def update_unit(unit_id: str, payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    require_unit_access(current_user)

    client = get_supabase_client()
    cleaned = {k: clean(v) for k, v in payload.items()}

    try:
        result = (
            client.table("units")
            .update(cleaned)
            .eq("id", unit_id)
            .select("*")
            .single()
            .execute()
        )
        return result.data
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
    require_unit_access(current_user)

    client = get_supabase_client()
    try:
        result = (
            client.table("units")
            .select("*")
            .eq("id", unit_id)
            .single()
            .execute()
        )
        return result.data
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
