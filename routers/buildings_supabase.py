from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser,
)


from core.supabase_client import get_supabase_client
from models.building import BuildingCreate, BuildingUpdate, BuildingRead
from core.supabase_helpers import update_record, delete_record



router = APIRouter(
    prefix="/buildings",
    tags=["Buildings"]
)

"""
BUILDINGS ROUTER (SUPABASE-ONLY)

All building data now lives in Supabase only.
This router exposes CRUD operations on the 'buildings' table.
Role protection:
  - List: authenticated users
  - Create: admin only
  - Update: admin or manager
  - Delete: admin only
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
    current_user: dict = Depends(get_current_user)
):
    # Any authenticated user is allowed — no RBAC check needed

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
# CREATE (Supabase) — ADMIN ONLY
# -----------------------------------------------------
@router.post(
    "/supabase",
    response_model=BuildingRead,
    summary="Create Building in Supabase"
)
def create_building_supabase(
    payload: BuildingCreate,
    current_user: CurrentUser = Depends(get_current_user)
):
    # 🔒 Only admins can create buildings
    requires_role(current_user, ["admin"])

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=500,
            detail="Supabase client not configured"
        )

    # Convert incoming payload → dict
    data = payload.dict()

    try:
        # Direct INSERT (preferred)
        result = (
            client.table("buildings")
            .insert(data)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=500,
                detail="Insert succeeded but no data returned"
            )

        return result.data[0]

    except Exception as e:
        msg = str(e)

        # Duplicate row / conflict
        if "duplicate key" in msg or "duplicate" in msg.lower():
            raise HTTPException(
                status_code=400,
                detail=f"Building '{payload.name}' already exists."
            )

        raise HTTPException(
            status_code=500,
            detail=f"Supabase insert error: {msg}"
        )


# -----------------------------------------------------
# UPDATE (Supabase) — ADMIN + MANAGER
# -----------------------------------------------------
@router.put(
    "/supabase/{building_id}",
    summary="Update Building in Supabase"
)
def update_building_supabase(
    building_id: str,
    payload: BuildingUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    requires_role(current_user, ["admin", "manager"])

    client = get_supabase_client()

    update_data = payload.model_dump(exclude_unset=True)

    # 💥 DEBUG LOG — this will print to your Render logs
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
            raise HTTPException(
                status_code=404,
                detail=f"Building with id '{building_id}' not found."
            )

        return result.data[0]

    except Exception as e:
        print("SUPABASE ERROR:", str(e))  # <--- THIS WILL SHOW THE REAL ERROR
        raise HTTPException(
            status_code=500,
            detail=f"Supabase update failed: {str(e)}"
        )


# -----------------------------------------------------
# DELETE (Supabase) — ADMIN ONLY
# -----------------------------------------------------
@router.delete("/{building_id}", summary="Delete a building (Admin only)")
def delete_building(
    building_id: str,
    current_user: CurrentUser = Depends(requires_role("admin")),
):
    client = get_supabase_client()

    try:
        result = (
            client.table("buildings")
            .delete()
            .eq("id", building_id)
            .execute()
        )

        # Supabase returns [] if nothing deleted
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Building ID {building_id} not found",
            )

        return {"status": "deleted", "id": building_id}

    except Exception as e:
        # Show REAL Supabase error in logs
        print("❌ Supabase delete error:", e)
        raise HTTPException(status_code=500, detail=str(e))
