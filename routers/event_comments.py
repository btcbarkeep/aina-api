from fastapi import APIRouter, Depends, HTTPException
from typing import List

from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser,
)

from core.supabase_client import get_supabase_client
from models.event_comment import (
    EventCommentCreate,
    EventCommentUpdate,
    EventCommentRead,
)

router = APIRouter(
    prefix="/event_comments",
    tags=["Event Comments"]
)

"""
EVENT COMMENTS ROUTER (SUPABASE)

Rules:
- Any authenticated user WITH BUILDING ACCESS may LIST comments
- Any authenticated user WITH BUILDING ACCESS may CREATE comments
- Only ADMINS may UPDATE or DELETE comments
"""

# -----------------------------------------------------
# Helper: event_id → building_id
# -----------------------------------------------------
def get_event_building_id(event_id: str) -> str:
    client = get_supabase_client()

    result = (
        client.table("events")
        .select("building_id")
        .eq("id", event_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    return result.data["building_id"]


# -----------------------------------------------------
# Helper: check building access
# -----------------------------------------------------
def verify_user_building_access_supabase(user_id: str, building_id: str):
    client = get_supabase_client()

    result = (
        client.table("user_building_access")
        .select("id")
        .eq("user_id", user_id)
        .eq("building_id", building_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission for this building."
        )


# -----------------------------------------------------
# LIST COMMENTS (must have building access)
# -----------------------------------------------------
@router.get(
    "/supabase/{event_id}",
    response_model=List[EventCommentRead],
    summary="List comments for an event"
)
def list_event_comments(
    event_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    building_id = get_event_building_id(event_id)
    verify_user_building_access_supabase(current_user.user_id, building_id)

    result = (
        client.table("event_comments")
        .select("*")
        .eq("event_id", event_id)
        .order("created_at", desc=False)
        .execute()
    )

    return result.data or []


# -----------------------------------------------------
# CREATE COMMENT (must have building access)
# -----------------------------------------------------
@router.post(
    "/supabase",
    response_model=EventCommentRead,
    summary="Create a comment for an event"
)
def create_event_comment(
    payload: EventCommentCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    building_id = get_event_building_id(payload.event_id)
    verify_user_building_access_supabase(current_user.user_id, building_id)

    comment_data = {
        "event_id": payload.event_id,
        "user_id": current_user.user_id,
        "comment_text": payload.comment_text,
    }

    result = client.table("event_comments").insert(comment_data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Supabase insert failed")

    return result.data[0]


# -----------------------------------------------------
# UPDATE COMMENT — ADMIN ONLY
# -----------------------------------------------------
@router.put(
    "/supabase/{comment_id}",
    response_model=EventCommentRead,
    summary="Update a comment (admin only)",
    dependencies=[Depends(requires_role(["admin"]))],
)
def update_event_comment(
    comment_id: str,
    payload: EventCommentUpdate,
):
    client = get_supabase_client()

    update_data = payload.model_dump(exclude_unset=True)

    result = (
        client.table("event_comments")
        .update(update_data)
        .eq("id", comment_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Comment not found")

    return result.data[0]


# -----------------------------------------------------
# DELETE COMMENT — ADMIN ONLY
# -----------------------------------------------------
@router.delete(
    "/supabase/{comment_id}",
    summary="Delete a comment (admin only)",
    dependencies=[Depends(requires_role(["admin"]))],
)
def delete_event_comment(
    comment_id: str,
):
    client = get_supabase_client()

    result = (
        client.table("event_comments")
        .delete()
        .eq("id", comment_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Comment not found")

    return {
        "status": "deleted",
        "id": comment_id,
        "message": "Comment deleted successfully."
    }
