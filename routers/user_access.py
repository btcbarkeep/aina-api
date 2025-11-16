from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.supabase_client import get_supabase_client
from dependencies.auth import get_current_user, CurrentUser, requires_role


router = APIRouter(
    prefix="/user-access",
    tags=["User Access"],
)


# ============================================================
# Helper — sanitize blanks → None
# ============================================================
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        if isinstance(v, str) and v.strip() == "":
            clean[k] = None
        else:
            clean[k] = v
    return clean


# ============================================================
# Pydantic Models
# ============================================================
class UserBuildingAccessCreate(BaseModel):
    user_id: str        # Supabase UUID
    building_id: str    # Supabase UUID


class UserBuildingAccessRead(BaseModel):
    user_id: str
    building_id: str


# ============================================================
# Admin — List all access
# ============================================================
@router.get(
    "/",
    summary="Admin: List all user building access entries",
    dependencies=[Depends(requires_role(["admin"]))],
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
# ============================================================
def validate_user_and_building(client, user_id: str, building_id: str):
    # Validate user
    user = (
        client.table("users")
        .select("id")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not user.data:
        raise HTTPException(404, f"User {user_id} not found")

    # Validate building
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
    summary="Admin: Grant a user building access",
    dependencies=[Depends(requires_role(["admin"]))],
)
def add_user_access(payload: UserBuildingAccessCreate):
    client = get_supabase_client()

    # Validate foreign keys
    validate_user_and_building(client, payload.user_id, payload.building_id)

    # Prevent duplicates
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
# Admin — Remove access
# ============================================================
@router.delete(
    "/{user_id}/{building_id}",
    summary="Admin: Remove building access for a user",
    dependencies=[Depends(requires_role(["admin"]))],
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

    # Bootstrap admin universal access
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
            .eq("user_id", current_user.id)     # <-- FIXED
            .execute()
        )

        return result.data or []

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")
