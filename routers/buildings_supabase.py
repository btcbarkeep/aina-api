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
BUILDINGS ROUTER (SUPABASE-ONLY)

All building data now lives in Supabase only.

Role protection:
  - List: authenticated users
  - Create: admin only
  - Update: admin or manager
  - Delete: admin only
"""

# -------------------------------------------------------------------
# LIST — Any authenticated user
# -------------------------------------------------------------------
@router.get("/supabase", summary="List Buildings from Supabase")
def list_buildings_supabase(
    limit: int = 100,
    name: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user)
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


# -------------------------------------------------------------------
# CREATE — Admin only
# -------------------------------------------------------------------
@router.post(
    "/supabase",
    response_model=BuildingRead,
    summary="Create Building in Supabase",
    dependencies=[Depends(requires_role(["admin"]))]
)
def create_building_supabase(
    payload: BuildingCreate,
):
    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase client not configured")

    data = payload.model_dump()

    try:
        result = client.table("buildings").insert(data).execute()

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


# -------------------------------------------------------------------
# UPDATE — Admin or Manager
# -------------------------------------------------------------------
@router.put(
    "/supabase/{building_id}",
    summary="Update Building in Supabase",
    dependencies=[Depends(requires_role(["admin", "manager"]))],
)
def update_building_supabase(
    building_id: str,
    payload: BuildingUpdate,
):
    client = get_supabase_client()

    update_data = payload.model_dump(exclude_unset=True)

    print("UPDATE BUILDING DEBUG:")
    print("building_id:", building_id)
    print("update_data:", update_data)

    try:
        result = (
            client.table("buildings")
            .update(update_data)
            .eq("id", building_id)
            .execute()
        )

        print("SUPABASE RESULT:", result)

        if not result.data:
            raise HTTPException(404, f"Building with id '{building_id}' not found.")

        return result.data[0]

    except Exception as e:
        print("SUPABASE ERROR:", str(e))
        raise HTTPException(500, f"Supabase update failed: {str(e)}")


# -------------------------------------------------------------------
# DELETE — Admin only
# -------------------------------------------------------------------
@router.delete(
    "/supabase/{building_id}",
    summary="Delete a building",
    dependencies=[Depends(requires_role(["admin"]))],
)
def delete_building(
    building_id: str,
):
    client = get_supabase_client()

    try:
        result = (
            client.table("buildings")
            .delete()
            .eq("id", building_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(404, f"Building '{building_id}' not found")

        return {"status": "deleted", "id": building_id}

    except Exception as e:
        print("❌ Supabase delete error:", e)
        raise HTTPException(500, str(e))
