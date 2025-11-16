# routers/contractors_supabase.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional

from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser,
)

from core.supabase_client import get_supabase_client
from core.supabase_helpers import update_record

from pydantic import BaseModel


router = APIRouter(
    prefix="/contractors",
    tags=["Contractors"],
)

# -----------------------------------------------------
# Helper — sanitize payload
# -----------------------------------------------------
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        if isinstance(v, str) and v.strip() == "":
            clean[k] = None
        else:
            clean[k] = v
    return clean


# -----------------------------------------------------
# Permission — Contractor Access Rules
# -----------------------------------------------------
def ensure_contractor_access(current_user: CurrentUser, contractor_id: str):
    """
    Contractors can only see THEIR own events & data.
    Admin + Manager can see all.
    Other roles cannot see contractor data.
    """
    if current_user.role in ["admin", "manager"]:
        return

    if current_user.role == "contractor":
        if current_user.contractor_id != contractor_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this contractor's data."
            )
        return

    raise HTTPException(status_code=403, detail="Access denied.")


# -----------------------------------------------------
# Pydantic Models
# -----------------------------------------------------
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


# -----------------------------------------------------
# LIST CONTRACTORS — any authenticated user
# -----------------------------------------------------
@router.get(
    "/",
    response_model=List[ContractorRead],
    summary="List all contractors"
)
def list_contractors(
    current_user: CurrentUser = Depends(get_current_user)
):
    client = get_supabase_client()

    result = (
        client.table("contractors")
        .select("*")
        .order("company_name", desc=False)
        .execute()
    )

    return result.data or []


# -----------------------------------------------------
# GET SINGLE CONTRACTOR
# -----------------------------------------------------
@router.get(
    "/{contractor_id}",
    response_model=ContractorRead,
    summary="Get contractor by ID"
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
        raise HTTPException(status_code=404, detail="Contractor not found")

    return result.data


# -----------------------------------------------------
# CREATE CONTRACTOR — Admin Only
# -----------------------------------------------------
@router.post(
    "/",
    response_model=ContractorRead,
    dependencies=[Depends(requires_role(["admin"]))],
    summary="Create a contractor (Admin only)"
)
def create_contractor(
    payload: ContractorCreate,
):
    client = get_supabase_client()
    data = sanitize(payload.model_dump())

    result = (
        client.table("contractors")
        .insert(data)
        .select("*")
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="Insert failed")

    return result.data[0]


# -----------------------------------------------------
# UPDATE CONTRACTOR — Admin Only
# -----------------------------------------------------
@router.put(
    "/{contractor_id}",
    response_model=ContractorRead,
    dependencies=[Depends(requires_role(["admin"]))],
    summary="Update a contractor (Admin only)",
)
def update_contractor(
    contractor_id: str,
    payload: ContractorUpdate,
):
    update_data = sanitize(payload.model_dump(exclude_unset=True))

    result = update_record("contractors", contractor_id, update_data)

    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return result["data"]


# -----------------------------------------------------
# DELETE CONTRACTOR — Admin Only (safe delete)
# -----------------------------------------------------
@router.delete(
    "/{contractor_id}",
    dependencies=[Depends(requires_role(["admin"]))],
    summary="Delete a contractor (Admin only)"
)
def delete_contractor(contractor_id: str):
    client = get_supabase_client()

    # Safety check — prevent deleting contractors with events
    events = (
        client.table("events")
        .select("id")
        .eq("contractor_id", contractor_id)
        .execute()
    )

    if events.data:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete contractor: events reference this contractor."
        )

    result = (
        client.table("contractors")
        .delete()
        .eq("id", contractor_id)
        .select("*")
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Contractor not found")

    return {"status": "deleted", "id": contractor_id}


# -----------------------------------------------------
# GET EVENTS FOR CONTRACTOR
# -----------------------------------------------------
@router.get(
    "/{contractor_id}/events",
    summary="List all events performed by this contractor",
)
def get_contractor_events(
    contractor_id: str,
    limit: int = 200,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_contractor_access(current_user, contractor_id)

    client = get_supabase_client()
    result = (
        client.table("events")
        .select("*")
        .eq("contractor_id", contractor_id)
        .order("occurred_at", desc=True)
        .limit(limit)
        .execute()
    )

    return result.data or []


# -----------------------------------------------------
# GET BUILDINGS WHERE CONTRACTOR HAS WORKED
# -----------------------------------------------------
@router.get(
    "/{contractor_id}/buildings",
    summary="List buildings this contractor has worked in",
)
def get_contractor_buildings(
    contractor_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_contractor_access(current_user, contractor_id)

    client = get_supabase_client()
    result = (
        client.table("events")
        .select("building_id")
        .eq("contractor_id", contractor_id)
        .execute()
    )

    if not result.data:
        return []

    unique_ids = sorted({row["building_id"] for row in result.data})

    buildings = (
        client.table("buildings")
        .select("*")
        .in_("id", unique_ids)
        .execute()
    )

    return buildings.data or []


# -----------------------------------------------------
# CONTRACTOR STATS — event breakdown
# -----------------------------------------------------
@router.get(
    "/{contractor_id}/stats",
    summary="Get contractor event statistics & breakdown",
)
def get_contractor_stats(
    contractor_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_contractor_access(current_user, contractor_id)

    client = get_supabase_client()
    result = (
        client.table("events")
        .select("severity,status,event_type")
        .eq("contractor_id", contractor_id)
        .execute()
    )

    rows = result.data or []

    def count_by(field: str):
        counter = {}
        for r in rows:
            value = r.get(field)
            if value:
                counter[value] = counter.get(value, 0) + 1
        return counter

    return {
        "total_events": len(rows),
        "by_severity": count_by("severity"),
        "by_status": count_by("status"),
        "by_type": count_by("event_type"),
    }
