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
from core.supabase_helpers import safe_update

router = APIRouter(
    prefix="/contractors",
    tags=["Contractors"],
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
# Helper — Check contractor access
# ============================================================
def ensure_contractor_access(current_user: CurrentUser, contractor_id: str):
    """
    Admin, super_admin, manager → full access
    Contractor → can only access their own contractor_id
    """
    if current_user.role in ["admin", "super_admin", "manager"]:
        return

    # Contractors now store contractor_id in Supabase Auth metadata
    if (
        current_user.role == "contractor"
        and current_user.contractor_id == contractor_id
    ):
        return

    raise HTTPException(403, "Insufficient permissions")


# ============================================================
# Pydantic Models
# ============================================================
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


# ============================================================
# LIST CONTRACTORS
# ============================================================
@router.get("", response_model=List[ContractorRead])
def list_contractors(current_user: CurrentUser = Depends(get_current_user)):
    if current_user.role not in ["admin", "super_admin", "manager"]:
        raise HTTPException(403, "Only admin/manager roles can list all contractors.")

    client = get_supabase_client()
    result = client.table("contractors").select("*").order("company_name").execute()
    return result.data or []


# ============================================================
# GET CONTRACTOR
# ============================================================
@router.get("/{contractor_id}", response_model=ContractorRead)
def get_contractor(contractor_id: str, current_user: CurrentUser = Depends(get_current_user)):
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


# ============================================================
# CREATE CONTRACTOR
# ============================================================
@router.post("", response_model=ContractorRead, dependencies=[Depends(requires_permission("contractors:write"))])
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


# ============================================================
# UPDATE CONTRACTOR
# ============================================================
@router.put("/{contractor_id}", response_model=ContractorRead, dependencies=[Depends(requires_permission("contractors:write"))])
def update_contractor(contractor_id: str, payload: ContractorUpdate):
    update_data = sanitize(payload.model_dump(exclude_unset=True))
    updated = safe_update("contractors", {"id": contractor_id}, update_data)

    if not updated:
        raise HTTPException(404, "Contractor not found")

    return updated


# ============================================================
# DELETE CONTRACTOR
# ============================================================
@router.delete("/{contractor_id}", dependencies=[Depends(requires_permission("contractors:write"))])
def delete_contractor(contractor_id: str):
    client = get_supabase_client()

    # Cannot delete contractor if events reference it
    events = (
        client.table("events")
        .select("id")
        .eq("created_by", contractor_id)
        .execute()
    )

    if events.data:
        raise HTTPException(400, "Cannot delete contractor — events reference this contractor.")

    result = (
        client.table("contractors")
        .delete(returning="representation")
        .eq("id", contractor_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(404, "Contractor not found")

    return {"status": "deleted", "id": contractor_id}
