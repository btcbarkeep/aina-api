# routers/buildings.py

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from dependencies.auth import get_current_user
from core.supabase_client import get_supabase_client
from models.building import BuildingCreate, BuildingUpdate, BuildingRead
from core.supabase_helpers import update_record, delete_record


router = APIRouter(
    prefix="/buildings",
    tags=["Buildings"]
)

"""
BUILDINGS ROUTER (SUPABASE-ONLY)

All building data is stored in Supabase using UUID primary keys.
This router exposes clean CRUD operations on the 'buildings' table.
"""


# -----------------------------------------------------
# LIST BUILDINGS (Supabase)
# -----------------------------------------------------
@router.get("/supabase", summary="List Buildings from Supabase")
def list_buildings_supabase(
    limit: int = 100,
    name: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

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


# -----------------------------------------------------
# CREATE BUILDING (Supabase)
# -----------------------------------------------------
@router.post(
    "/supabase",
    response_model=BuildingRead,
    summary="Create Building in Supabase"
)
def create_building_supabase(
    payload: BuildingCreate,
    current_user: dict = Depends(get_current_user),
):
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        data = payload.dict()

        # Insert (do NOT upsert by name anymore – now using UUID PK)
        result = client.table("buildings").insert(data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Supabase insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")


# -----------------------------------------------------
# UPDATE BUILDING (Supabase)
# -----------------------------------------------------
@router.put(
    "/supabase/{building_id}",
    summary="Update Building in Supabase"
)
def update_building_supabase(
    building_id: str,
    payload: BuildingUpdate,
    current_user: dict = Depends(get_current_user),
):
    update_data = payload.dict(exclude_unset=True)

    result = update_record("buildings", building_id, update_data)

    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return result["data"]


# -----------------------------------------------------
# DELETE BUILDING (Supabase)
# -----------------------------------------------------
@router.delete(
    "/supabase/{building_id}",
    summary="Delete Building in Supabase"
)
def delete_building_supabase(
    building_id: str,
    current_user: dict = Depends(get_current_user),
):
    result = delete_record("buildings", building_id)

    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return {"status": "deleted", "id": building_id}
