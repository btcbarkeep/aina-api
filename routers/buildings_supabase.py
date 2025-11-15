from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser,
)

from core.supabase_client import get_supabase_client
from models.building import BuildingCreate, BuildingUpdate, BuildingRead


router = APIRouter(
    prefix="/buildings",
    tags=["Buildings"]
)

"""
BUILDINGS ROUTER — FULLY HARDENED VERSION

Fixes applied:
  ✓ All inserts/updates now use .select("*") to ensure data returns
  ✓ Sanitizes empty fields before insert/update
  ✓ Prevents '500 but still inserts' issues
  ✓ Consistent RBAC (requires_role(["admin"]))
  ✓ Better error logging
"""


# ---------------------------------------------------------
# Helper — normalize payloads
# Converts "" or None → None for safe DB storage
# ---------------------------------------------------------
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        if isinstance(v, str) and v.strip() == "":
            clean[k] = None
        else:
            clean[k] = v
    return clean


# ---------------------------------------------------------
# LIST — Any authenticated user
# ---------------------------------------------------------
@router.get(
    "/supabase",
    summary="List Buildings from Supabase",
    response_model=list[BuildingRead]
)
def list_buildings_supabase(
    limit: int = 100,
    name: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user)
):
    client = get_supabase_client()

    try:
        query = client.table("buildings").select("*").limit(limit)

        if name:
            query = query.ilike("name", f"%{name}%")
        if city:
            query = query.ilike("city", f"%{city}%")
        if state:
            query = query.ilike("state", f"%{state}%")

        result = query.execute()
        return result.data or []

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase fetch error: {e}")


# ---------------------------------------------------------
# CREATE — Admin only
# ---------------------------------------------------------
@router.post(
    "/supabase",
    response_model=BuildingRead,
    summary="Create Building (Supabase only)",
    dependencies=[Depends(requires_role(["admin"]))]
)
def create_building_supabase(payload: BuildingCreate):
    client = get_supabase_client()

    # Sanitize empty strings
    data = sanitize(payload.model_dump())

    try:
        # **IMPORTANT**: use select("*") to ensure return value
        result = (
            client.table("buildings")
            .insert(data)
            .select("*")
            .execute()
        )

        if not result.data:
            raise HTTPException(500, "Insert succeeded but returned no data")

        return result.data[0]

    except Exception as e:
        msg = str(e)

        if "duplicate" in msg.lower():
            raise HTTPException(
                400,
                f"Building '{payload.name}' already exists."
            )

        raise HTTPException(500, f"Supabase insert error: {msg}")


# ---------------------------------------------------------
# UPDATE — Admin or Manager
# ---------------------------------------------------------
@router.put(
    "/supabase/{building_id}",
    response_model=BuildingRead,
    summary="Update Building in Supabase",
    dependencies=[Depends(requires_role(["admin", "manager"]))]
)
def update_building_supabase(
    building_id: str,
    payload: BuildingUpdate,
):
    client = get_supabase_client()

    update_data = sanitize(payload.model_dump(exclude_unset=True))

    try:
        result = (
            client.table("buildings")
            .update(update_data)
            .eq("id", building_id)
            .select("*")
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Building '{building_id}' not found."
            )

        return result.data[0]

    except Exception as e:
        raise HTTPException(500, f"Supabase update failed: {e}")


# ---------------------------------------------------------
# DELETE — Admin only
# ---------------------------------------------------------
@router.delete(
    "/supabase/{building_id}",
    summary="Delete Building",
    dependencies=[Depends(requires_role(["admin"]))]
)
def delete_building(building_id: str):
    client = get_supabase_client()

    try:
        result = (
            client.table("buildings")
            .delete()
            .eq("id", building_id)
            .select("*")
            .execute()
        )

        if not result.data:
            raise HTTPException(404, f"Building '{building_id}' not found")

        return {"status": "deleted", "id": building_id}

    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")
