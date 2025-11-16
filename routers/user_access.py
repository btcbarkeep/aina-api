# routers/user_access.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List

from core.supabase_client import get_supabase_client
from dependencies.auth import get_current_user, CurrentUser, requires_role
from pydantic import BaseModel

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
# Admin — List all user access entries
# ============================================================
@router.get(
    "/",
    summary="Admin: List all user access records",
    dependencies=[Depends(requires_role(["admin"]))],
)
def list_user_access():
    client = get_supabase_client()

    try:
        result = client.table("user_building_access").select("user_id, building_id").execute()
        return result.data or []
    except Exception as e:
        raise HTTPException(500, f"Supabase query failed: {e}")


# ============================================================
# Admin — Grant user access to a building
# ============================================================
@router.post(
    "/",
    summary="Admin: Add user → building access",
    dependencies=[Depends(requires_role(["admin"]))],
)
def add_user_access(payload: UserBuildingAccessCreate):
    client = get_supabase_client()

    try:
        result = (
            client.table("user_building_access")
            .insert({
                "user_id": payload.user_id,
                "building_id": payload.building_id,
            })
            .execute()
        )
        return result.data[0]

    except Exception as e:
        raise HTTPException(500, f"Supabase insert failed: {e}")


# ============================================================
# Admin — Remove a user’s building access
# ============================================================
@router.delete(
    "/{user_id}/{building_id}",
    summary="Admin: Delete a user access entry",
    dependencies=[Depends(requires_role(["admin"]))],
)
def delete_user_access(user_id: str, building_id: str):
    client = get_supabase_client()

    try:
        result = (
            client.table("user_building_access")
            .delete()
            .eq("user_id", user_id)
            .eq("building_id", building_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(404, "Access record not found")

        return {"status": "deleted", "user_id": user_id, "building_id": building_id}

    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")


# ============================================================
# User — See their own building access list
# ============================================================
@router.get("/me", summary="Get buildings the current user has access to")
def my_access(current_user: CurrentUser = Depends(get_current_user)):
    """
    Returns all building IDs that the authenticated user can manage.
    Accessible by ANY logged-in user.
    """
    client = get_supabase_client()

    try:
        result = (
            client.table("user_building_access")
            .select("building_id")
            .eq("user_id", current_user.username)  # FIXED
            .execute()
        )
        return result.data or []

    except Exception as e:
        raise HTTPException(500, f"Supabase fetch failed: {e}")
