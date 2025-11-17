# routers/contractors.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
from core.supabase_helpers import update_record


router = APIRouter(
    prefix="/contractors",
    tags=["Contractors"],
)

# ------------------------------------------------------------
# Helper — sanitize input
# ------------------------------------------------------------
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        if isinstance(v, str) and v.strip() == "":
            clean[k] = None
        else:
            clean[k] = v
    return clean


# ------------------------------------------------------------
# Contractor access logic
# ------------------------------------------------------------
def ensure_contractor_access(current_user: CurrentUser, contractor_id: str):
    """
    Access rules under permission system:

      • contractors:read allows admins/managers/etc. to read ANY contractor
      • contractors:write allows create/update/delete of ANY contractor

      • contractors with role "contractor" can ONLY access their own ID,
        regardless of permissions
    """
    # Contractors restricted to themselves
    if current_user.role == "contractor":
        if current_user.id != contractor_id:
            raise HTTPException(403, "Contractors may only access their own profile.")


# ------------------------------------------------------------
# Models
# ------------------------------------------------------------
class ContractorBase(BaseModel):
    company_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    license_number: Optional[str] = None
    insurance_info: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None


class ContractorCreate(ContractorBase):
    pass


class ContractorRead(ContractorBase):
    id: str
    created_at: Optional[str] = None


class ContractorUpdate(BaseModel):
    company_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    license_number: Optional[str] = None
    insurance_info: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None


# ------------------------------------------------------------
# LIST CONTRACTORS
# ------------------------------------------------------------
@router.get(
    "/",
    response_model=List[ContractorRead],
    summary="List all contractors",
    dependencies=[Depends(requires_permission("contractors:read"))],
)
def list_contractors():
    client = get_supabase_client()

    result = (
        client.table("contractors")
        .select("*")
        .order("company_name", desc=False)
        .execute()
    )

    return result.data or []


# ------------------------------------------------------------
# GET A CONTRACTOR
# ------------------------------------------------------------
@router.get(
    "/{contractor_id}",
    response_model=ContractorRead,
    summary="Get contractor profile",
    dependencies=[Depends(requires_permission("contractors:read"))],
)
def get_contractor(
    contractor_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_contractor_access(current_user, contractor_id)

    client = get_supabase_client()

    result = (
        client.table("contractors")
        .select("*")
        .eq("id", contractor_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(404, "Contractor not found")

    return result.data


# ------------------------------------------------------------
# CREATE CONTRACTOR
# ------------------------------------------------------------
@router.post(
    "/",
    response_model=ContractorRead,
    summary="Create contractor",
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def create_contractor(payload: ContractorCreate):
    client = get_supabase_client()
    data = sanitize(payload.model_dump())

    result = (
        client.table("contractors")
        .insert(data, returning="representation")
        .execute()
    )

    if not result.data:
        raise HTTPException(500, "Failed to create contractor")

    return result.data[0]


# ------------------------------------------------------------
# UPDATE CONTRACTOR
# ------------------------------------------------------------
@router.put(
    "/{contractor_id}",
    response_model=ContractorRead,
    summary="Update contractor",
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def update_contractor(
    contractor_id: str,
    payload: ContractorUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_contractor_access(current_user, contractor_id)

    update_data = sanitize(payload.model_dump(exclude_unset=True))

    result = update_record("contractors", contractor_id, update_data)

    if result["status"] != "ok":
        raise HTTPException(500, result["detail"])

    return result["data"]


# ------------------------------------------------------------
# DELETE CONTRACTOR
# ------------------------------------------------------------
@router.delete(
    "/{contractor_id}",
    summary="Delete contractor",
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def delete_contractor(
    contractor_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_contractor_access(current_user, contractor_id)

    client = get_supabase_client()

    # Cannot delete if contractor has events
    events = (
        client.table("events")
        .select("id")
        .eq("created_by", contractor_id)
        .execute()
    )

    if events.data:
        raise HTTPException(
            400,
            "Cannot delete contractor — events reference this contractor.",
        )

    result = (
        client.table("contractors")
        .delete(returning="representation")
        .eq("id", contractor_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(404, "Contractor not found")

    return {"status": "deleted", "id": contractor_id}


# ------------------------------------------------------------
# CONTRACTOR → EVENTS
# ------------------------------------------------------------
@router.get(
    "/{contractor_id}/events",
    summary="List events submitted by this contractor",
    dependencies=[Depends(requires_permission("contractor_events:read"))],
)
def contractor_events(
    contractor_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_contractor_access(current_user, contractor_id)

    client = get_supabase_client()

    result = (
        client.table("events")
        .select("*")
        .eq("created_by", contractor_id)
        .order("occurred_at", desc=True)
        .execute()
    )

    return result.data or []


# ------------------------------------------------------------
# CONTRACTOR → BUILDINGS
# ------------------------------------------------------------
@router.get(
    "/{contractor_id}/buildings",
    summary="List buildings this contractor worked in",
    dependencies=[Depends(requires_permission("contractor_events:read"))],
)
def contractor_buildings(
    contractor_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_contractor_access(current_user, contractor_id)

    client = get_supabase_client()

    events = (
        client.table("events")
        .select("building_id")
        .eq("created_by", contractor_id)
        .execute()
    ).data or []

    if not events:
        return []

    building_ids = sorted({e["building_id"] for e in events})

    buildings = (
        client.table("buildings")
        .select("*")
        .in_("id", building_ids)
        .execute()
    )

    return buildings.data or []


# ------------------------------------------------------------
# CONTRACTOR → STATS
# ------------------------------------------------------------
@router.get(
    "/{contractor_id}/stats",
    summary="Get contractor stats",
    dependencies=[Depends(requires_permission("contractor_events:read"))],
)
def contractor_stats(
    contractor_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_contractor_access(current_user, contractor_id)

    client = get_supabase_client()

    rows = (
        client.table("events")
        .select("severity,status,event_type")
        .eq("created_by", contractor_id)
        .execute()
    ).data or []

    def count(field):
        out = {}
        for r in rows:
            v = r.get(field)
            if v:
                out[v] = out.get(v, 0) + 1
        return out

    return {
        "total_events": len(rows),
        "by_severity": count("severity"),
        "by_status": count("status"),
        "by_type": count("event_type"),
    }
