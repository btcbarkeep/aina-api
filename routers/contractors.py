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
# Helper — role-based access rules (FIXED)
# ============================================================
def ensure_contractor_access(current_user: CurrentUser, contractor_id: str):
    """
    Admin, super_admin → full access
    Contractor → only access their own contractor_id
    """
    # Only admins bypass
    if current_user.role in ["admin", "super_admin"]:
        return

    # Contractors can only access their own record
    if (
        current_user.role == "contractor"
        and getattr(current_user, "contractor_id", None) == contractor_id
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
# LIST CONTRACTORS (FIXED: managers should NOT have global view)
# ============================================================
@router.get("", response_model=List[ContractorRead])
def list_contractors(current_user: CurrentUser = Depends(get_current_user)):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admin roles can list all contractors.")

    client = get_supabase_client()
    result = (
        client.table("contractors")
        .select("*")
        .order("company_name")
        .execute()
    )

    return result.data or []


# ============================================================
# GET CONTRACTOR — SAFE (NO .single())
# ============================================================
@router.get("/{contractor_id}", response_model=ContractorRead)
def get_contractor(contractor_id: str, current_user: CurrentUser = Depends(get_current_user)):
    ensure_contractor_access(current_user, contractor_id)

    client = get_supabase_client()
    rows = (
        client.table("contractors")
        .select("*")
        .eq("id", contractor_id)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(404, "Contractor not found")

    return rows[0]


# ============================================================
# CREATE CONTRACTOR — 2-STEP INSERT
# ============================================================
@router.post(
    "",
    response_model=ContractorRead,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def create_contractor(payload: ContractorCreate):
    client = get_supabase_client()
    data = sanitize(payload.model_dump())

    # Step 1 — Insert
    try:
        insert_res = client.table("contractors").insert(data).execute()
    except Exception as e:
        raise HTTPException(500, f"Supabase insert error: {e}")

    if not insert_res.data:
        raise HTTPException(500, "Insert returned no data")

    contractor_id = insert_res.data[0]["id"]

    # Step 2 — Fetch created contractor
    fetch_res = (
        client.table("contractors")
        .select("*")
        .eq("id", contractor_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Created contractor not found")

    return fetch_res.data[0]


# ============================================================
# UPDATE CONTRACTOR — 2-STEP UPDATE
# ============================================================
@router.put(
    "/{contractor_id}",
    response_model=ContractorRead,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def update_contractor(contractor_id: str, payload: ContractorUpdate):
    client = get_supabase_client()
    update_data = sanitize(payload.model_dump(exclude_unset=True))

    # Step 1 — update
    try:
        update_res = (
            client.table("contractors")
            .update(update_data)
            .eq("id", contractor_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    if not update_res.data:
        raise HTTPException(404, "Contractor not found")

    # Step 2 — fetch updated contractor
    fetch_res = (
        client.table("contractors")
        .select("*")
        .eq("id", contractor_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Updated contractor not found")

    return fetch_res.data[0]


# ============================================================
# DELETE CONTRACTOR — SAFE 2-STEP DELETE
# ============================================================
@router.delete(
    "/{contractor_id}",
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def delete_contractor(contractor_id: str):
    client = get_supabase_client()

    # Prevent deletion if referenced by events
    events = (
        client.table("events")
        .select("id")
        .eq("contractor_id", contractor_id)
        .execute()
    )

    if events.data:
        raise HTTPException(400, "Cannot delete contractor — events reference this contractor.")

    # Step 1 — delete
    try:
        delete_res = (
            client.table("contractors")
            .delete()
            .eq("id", contractor_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")

    if not delete_res.data:
        raise HTTPException(404, "Contractor not found")

    return {"status": "deleted", "id": contractor_id}
