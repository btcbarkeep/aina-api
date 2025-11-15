from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from dependencies.auth import get_current_user, requires_role, CurrentUser

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
    summary="Create or Upsert Building in Supabase"
)
def create_building_supabase(
    payload: BuildingCreate,
    current_user: dict = Depends(get_current_user)
):
    require_role(current_user, ["admin"])  # 🔒 Only admins can create

    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        data = payload.dict()

        result = client.table("buildings").upsert(
            data,
            on_conflict="name"
        ).execute()

        if not result.data:
            raise HTTPException(
                status_code=400,
                detail=f"Building '{payload.name}' already exists."
            )

        return result.data[0]

    except Exception as e:
        msg = str(e)
        raise HTTPException(status_code=500, detail=f"Supabase upsert error: {msg}")


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
    current_user: dict = Depends(get_current_user)
):
    require_role(current_user, ["admin", "manager"])  # 🔒 Allowed roles

    update_data = payload.dict(exclude_unset=True)

    result = update_record("buildings", building_id, update_data)

    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return result["data"]


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
