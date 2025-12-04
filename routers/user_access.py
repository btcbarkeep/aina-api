from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.supabase_client import get_supabase_client
from core.utils import sanitize
from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

router = APIRouter(
    prefix="/user-access",
    tags=["User Access"],
)


# ============================================================
# Pydantic Models
# ============================================================
class UserBuildingAccessCreate(BaseModel):
    user_id: str
    building_id: str


class UserBuildingAccessRead(BaseModel):
    user_id: str
    building_id: str


# ============================================================
# Admin — List all access (unchanged)
# ============================================================
@router.get(
    "/",
    summary="List all user building access entries",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_user_access():
    client = get_supabase_client()

    try:
        result = (
            client.table("user_building_access")
            .select("user_id, building_id")
            .execute()
        )
        return result.data or []

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# Helper — Validate User & Building exist
# NEW: user validation now checks Supabase Auth
# ============================================================
def validate_user_and_building(client, user_id: str, building_id: str):
    # 1️⃣ Validate user exists in Supabase Auth
    try:
        user_resp = client.auth.admin.get_user_by_id(user_id)
        if not user_resp or not user_resp.user:
            raise HTTPException(404, f"User {user_id} not found")
    except Exception as e:
        raise HTTPException(500, f"Supabase Auth user lookup failed: {e}")

    # 2️⃣ Validate building exists (unchanged)
    building = (
        client.table("buildings")
        .select("id")
        .eq("id", building_id)
        .single()
        .execute()
    )
    if not building.data:
        raise HTTPException(404, f"Building {building_id} not found")


# ============================================================
# Admin — Grant user access
# ============================================================
@router.post(
    "/",
    summary="Grant a user building access",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def add_user_access(payload: UserBuildingAccessCreate):
    client = get_supabase_client()

    # Validate existence
    validate_user_and_building(client, payload.user_id, payload.building_id)

    # Prevent duplicate access
    existing = (
        client.table("user_building_access")
        .select("user_id")
        .eq("user_id", payload.user_id)
        .eq("building_id", payload.building_id)
        .execute()
    )

    if existing.data:
        raise HTTPException(400, "User already has access to this building")

    try:
        clean_payload = sanitize(payload.model_dump())

        result = (
            client.table("user_building_access")
            .insert(clean_payload, returning="representation")
            .execute()
        )

        if not result.data:
            raise HTTPException(500, "Insert failed — no data returned")

        return result.data[0]

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# Admin — Remove user access
# ============================================================
@router.delete(
    "/{user_id}/{building_id}",
    summary="Remove building access for a user",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def delete_user_access(user_id: str, building_id: str):
    client = get_supabase_client()

    try:
        result = (
            client.table("user_building_access")
            .delete(returning="representation")
            .eq("user_id", user_id)
            .eq("building_id", building_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(404, "Access record not found")

        return {
            "status": "deleted",
            "user_id": user_id,
            "building_id": building_id,
        }

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# User — View their own building access
# ============================================================
@router.get("/me", summary="Get building access for the authenticated user")
def my_access(current_user: CurrentUser = Depends(get_current_user)):

    # Bootstrap admin = universal access, special-case
    if current_user.id == "bootstrap":
        return [{
            "building_id": "ALL",
            "note": "Bootstrap admin has universal access",
        }]

    client = get_supabase_client()

    try:
        result = (
            client.table("user_building_access")
            .select("building_id")
            .eq("user_id", current_user.id)
            .execute()
        )

        return result.data or []

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")
