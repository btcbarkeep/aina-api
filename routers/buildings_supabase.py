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
        raise HTTPException(500, "Supabase not configured")

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
        print("❌ ERROR in list_buildings_supabase:", str(e))
        raise HTTPException(500, f"Supabase fetch error: {str(e)}")


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
    data = sanitize(payload.model_dump())

    try:
        # 1️⃣ Insert
        insert_result = (
            client.table("buildings")
            .insert(data)
            .execute()
        )

        if not insert_result.data:
            raise HTTPException(500, "Insert succeeded but returned no data")

        building_id = insert_result.data[0]["id"]

        # 2️⃣ Fetch record
        fetch_result = (
            client.table("buildings")
            .select("*")
            .eq("id", building_id)
            .single()
            .execute()
        )

        return fetch_result.data

    except Exception as e:
        msg = str(e)
        if "duplicate" in msg.lower():
            raise HTTPException(400, f"Building '{payload.name}' already exists.")
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
        # 1️⃣ UPDATE (NO select() allowed here)
        update_result = (
            client.table("buildings")
            .update(update_data)
            .eq("id", building_id)
            .execute()
        )

        if update_result.data is None:
            raise HTTPException(
                404,
                f"Building '{building_id}' not found."
            )

        # 2️⃣ Fetch updated record
        fetch_result = (
            client.table("buildings")
            .select("*")
            .eq("id", building_id)
            .single()
            .execute()
        )

        if not fetch_result.data:
            raise HTTPException(404, f"Building '{building_id}' not found")

        return fetch_result.data

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
        delete_result = (
            client.table("buildings")
            .delete()
            .eq("id", building_id)
            .execute()
        )

        if not delete_result.data:
            raise HTTPException(404, f"Building '{building_id}' not found")

        return {"status": "deleted", "id": building_id}

    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")
