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


class UserUnitAccessCreate(BaseModel):
    user_id: str
    unit_id: str


class UserUnitAccessRead(BaseModel):
    user_id: str
    unit_id: str


# ============================================================
# Admin — List all building access
# ============================================================
@router.get(
    "/buildings",
    summary="List all user building access entries",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_building_access():
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
# Admin — List all unit access
# ============================================================
@router.get(
    "/units",
    summary="List all user unit access entries",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_unit_access():
    client = get_supabase_client()

    try:
        result = (
            client.table("user_units_access")
            .select("user_id, unit_id")
            .execute()
        )
        return result.data or []

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# Admin — List all access (both building and unit)
# ============================================================
@router.get(
    "/",
    summary="List all user access entries (buildings and units)",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_user_access():
    client = get_supabase_client()

    try:
        building_result = (
            client.table("user_building_access")
            .select("user_id, building_id")
            .execute()
        )
        unit_result = (
            client.table("user_units_access")
            .select("user_id, unit_id")
            .execute()
        )
        
        return {
            "buildings": building_result.data or [],
            "units": unit_result.data or [],
        }

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
        .limit(1)
        .execute()
    )
    if not building.data:
        raise HTTPException(404, f"Building {building_id} not found")


# ============================================================
# Helper — Validate User & Unit exist
# ============================================================
def validate_user_and_unit(client, user_id: str, unit_id: str):
    # 1️⃣ Validate user exists in Supabase Auth
    try:
        user_resp = client.auth.admin.get_user_by_id(user_id)
        if not user_resp or not user_resp.user:
            raise HTTPException(404, f"User {user_id} not found")
    except Exception as e:
        raise HTTPException(500, f"Supabase Auth user lookup failed: {e}")

    # 2️⃣ Validate unit exists
    unit = (
        client.table("units")
        .select("id")
        .eq("id", unit_id)
        .limit(1)
        .execute()
    )
    if not unit.data:
        raise HTTPException(404, f"Unit {unit_id} not found")


# ============================================================
# Admin — Grant user building access
# ============================================================
@router.post(
    "/buildings",
    summary="Grant a user building access",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def add_building_access(payload: UserBuildingAccessCreate):
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
# Admin — Grant user unit access
# ============================================================
@router.post(
    "/units",
    summary="Grant a user unit access",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def add_unit_access(payload: UserUnitAccessCreate):
    client = get_supabase_client()

    # Validate existence
    validate_user_and_unit(client, payload.user_id, payload.unit_id)

    # Prevent duplicate access
    existing = (
        client.table("user_units_access")
        .select("user_id")
        .eq("user_id", payload.user_id)
        .eq("unit_id", payload.unit_id)
        .execute()
    )

    if existing.data:
        raise HTTPException(400, "User already has access to this unit")

    try:
        clean_payload = sanitize(payload.model_dump())

        result = (
            client.table("user_units_access")
            .insert(clean_payload, returning="representation")
            .execute()
        )

        if not result.data:
            raise HTTPException(500, "Insert failed — no data returned")

        return result.data[0]

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# Admin — Remove user building access
# ============================================================
@router.delete(
    "/buildings/{user_id}/{building_id}",
    summary="Remove building access for a user",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def delete_building_access(user_id: str, building_id: str):
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
# Admin — Remove user unit access
# ============================================================
@router.delete(
    "/units/{user_id}/{unit_id}",
    summary="Remove unit access for a user",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def delete_unit_access(user_id: str, unit_id: str):
    client = get_supabase_client()

    try:
        result = (
            client.table("user_units_access")
            .delete(returning="representation")
            .eq("user_id", user_id)
            .eq("unit_id", unit_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(404, "Access record not found")

        return {
            "status": "deleted",
            "user_id": user_id,
            "unit_id": unit_id,
        }

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# Legacy endpoints — Backward compatibility
# ============================================================
@router.post(
    "/",
    summary="Grant a user building access (legacy endpoint)",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def add_user_access(payload: UserBuildingAccessCreate):
    """Legacy endpoint for backward compatibility. Use POST /buildings instead."""
    return add_building_access(payload)


@router.delete(
    "/{user_id}/{building_id}",
    summary="Remove building access for a user (legacy endpoint)",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def delete_user_access(user_id: str, building_id: str):
    """Legacy endpoint for backward compatibility. Use DELETE /buildings/{user_id}/{building_id} instead."""
    return delete_building_access(user_id, building_id)


# ============================================================
# User — View their own access (buildings and units)
# ============================================================
@router.get("/me", summary="Get building and unit access for the authenticated user")
def my_access(current_user: CurrentUser = Depends(get_current_user)):

    # Bootstrap admin = universal access, special-case
    if current_user.id == "bootstrap":
        return {
            "buildings": [{
                "building_id": "ALL",
                "note": "Bootstrap admin has universal access",
            }],
            "units": [{
                "unit_id": "ALL",
                "note": "Bootstrap admin has universal access",
            }],
        }

    client = get_supabase_client()
    user_id = current_user.auth_user_id  # Use auth_user_id for consistency

    try:
        building_result = (
            client.table("user_building_access")
            .select("building_id")
            .eq("user_id", user_id)
            .execute()
        )
        
        unit_result = (
            client.table("user_units_access")
            .select("unit_id")
            .eq("user_id", user_id)
            .execute()
        )

        return {
            "buildings": building_result.data or [],
            "units": unit_result.data or [],
        }

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")
