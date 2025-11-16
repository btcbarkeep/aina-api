# routers/contractor_events_supabase.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional

from dependencies.auth import (
    get_current_user,
    CurrentUser
)

from core.supabase_client import get_supabase_client

router = APIRouter(
    prefix="/contractors",
    tags=["Contractor Events"]
)

# -----------------------------------------------------
# GET ALL EVENTS BY CONTRACTOR
# -----------------------------------------------------
@router.get(
    "/{contractor_id}/events",
    summary="List all events associated with a contractor"
)
def list_contractor_events(
    contractor_id: str,
    building_id: Optional[str] = None,
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user)
):
    client = get_supabase_client()

    query = (
        client.table("events")
        .select("*")
        .eq("contractor_id", contractor_id)
        .order("occurred_at", desc=True)
    )

    if building_id:
        query = query.eq("building_id", building_id)
    if event_type:
        query = query.eq("event_type", event_type)
    if status:
        query = query.eq("status", status)

    result = query.execute()

    return result.data or []
