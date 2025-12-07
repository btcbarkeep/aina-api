# routers/aoao_organizations.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from dependencies.auth import get_current_user, CurrentUser, requires_permission
from core.supabase_client import get_supabase_client
from core.utils import sanitize
from core.logging_config import logger
from core.errors import handle_supabase_error
from models.aoao_organization import (
    AOAOOrganizationCreate,
    AOAOOrganizationUpdate,
    AOAOOrganizationRead
)
from models.enums import SubscriptionTier, SubscriptionStatus

router = APIRouter(
    prefix="/aoao-organizations",
    tags=["AOAO Organizations"],
)


# ============================================================
# LIST AOAO ORGANIZATIONS
# ============================================================
@router.get("", response_model=List[AOAOOrganizationRead])
def list_aoao_organizations(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of organizations to return (1-1000)"),
    search: Optional[str] = Query(None, description="Search organizations by name (case-insensitive)"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    List all AOAO organizations.
    
    Admin only.
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admins can list AOAO organizations")
    
    client = get_supabase_client()
    query = client.table("aoao_organizations").select("*")
    
    if search:
        query = query.ilike("organization_name", f"%{search}%")
    
    query = query.order("organization_name").limit(limit)
    result = query.execute()
    
    return result.data or []


# ============================================================
# GET AOAO ORGANIZATION
# ============================================================
@router.get("/{organization_id}", response_model=AOAOOrganizationRead)
def get_aoao_organization(
    organization_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get a specific AOAO organization.
    
    Admin only, or users linked to this organization.
    """
    client = get_supabase_client()
    
    # Check access
    if current_user.role not in ["admin", "super_admin"]:
        # Users can only access their own organization
        user_org_id = getattr(current_user, "aoao_organization_id", None)
        if user_org_id != organization_id:
            raise HTTPException(403, "Insufficient permissions")
    
    rows = (
        client.table("aoao_organizations")
        .select("*")
        .eq("id", organization_id)
        .limit(1)
        .execute()
    ).data
    
    if not rows:
        raise HTTPException(404, "AOAO organization not found")
    
    return rows[0]


# ============================================================
# CREATE AOAO ORGANIZATION
# ============================================================
@router.post(
    "",
    response_model=AOAOOrganizationRead,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def create_aoao_organization(payload: AOAOOrganizationCreate):
    """
    Create a new AOAO organization.
    
    Admin only.
    """
    client = get_supabase_client()
    
    # Check for duplicate organization name (case-insensitive)
    org_name = payload.organization_name.strip()
    existing = (
        client.table("aoao_organizations")
        .select("id, organization_name")
        .ilike("organization_name", org_name)
        .limit(1)
        .execute()
    )
    
    if existing.data:
        raise HTTPException(
            400,
            f"AOAO organization with name '{org_name}' already exists. Organization names must be unique."
        )
    
    # Prepare data
    data = sanitize(payload.model_dump())
    
    # Convert enum fields to strings for database
    if "subscription_tier" in data and data["subscription_tier"]:
        data["subscription_tier"] = str(data["subscription_tier"])
    if "subscription_status" in data and data["subscription_status"]:
        data["subscription_status"] = str(data["subscription_status"])
    
    try:
        insert_res = client.table("aoao_organizations").insert(data).execute()
        if not insert_res.data:
            raise HTTPException(500, "Failed to create AOAO organization")
        return insert_res.data[0]
    except Exception as e:
        handle_supabase_error(e, "Failed to create AOAO organization")


# ============================================================
# UPDATE AOAO ORGANIZATION
# ============================================================
@router.patch(
    "/{organization_id}",
    response_model=AOAOOrganizationRead,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def update_aoao_organization(
    organization_id: str,
    payload: AOAOOrganizationUpdate
):
    """
    Update an AOAO organization.
    
    Admin only.
    """
    client = get_supabase_client()
    
    # Check if organization exists
    existing = (
        client.table("aoao_organizations")
        .select("id")
        .eq("id", organization_id)
        .limit(1)
        .execute()
    )
    
    if not existing.data:
        raise HTTPException(404, "AOAO organization not found")
    
    # Check for duplicate name if updating
    if payload.organization_name:
        org_name = payload.organization_name.strip()
        duplicate = (
            client.table("aoao_organizations")
            .select("id, organization_name")
            .ilike("organization_name", org_name)
            .neq("id", organization_id)
            .limit(1)
            .execute()
        )
        
        if duplicate.data:
            raise HTTPException(
                400,
                f"AOAO organization with name '{org_name}' already exists."
            )
    
    # Prepare update data
    updates = sanitize(payload.model_dump(exclude_unset=True))
    
    # Convert enum fields to strings
    if "subscription_tier" in updates and updates["subscription_tier"]:
        updates["subscription_tier"] = str(updates["subscription_tier"])
    if "subscription_status" in updates and updates["subscription_status"]:
        updates["subscription_status"] = str(updates["subscription_status"])
    
    if not updates:
        raise HTTPException(400, "No fields provided to update")
    
    try:
        update_res = (
            client.table("aoao_organizations")
            .update(updates)
            .eq("id", organization_id)
            .execute()
        )
        
        if not update_res.data:
            raise HTTPException(500, "Failed to update AOAO organization")
        
        return update_res.data[0]
    except Exception as e:
        handle_supabase_error(e, "Failed to update AOAO organization")


# ============================================================
# DELETE AOAO ORGANIZATION
# ============================================================
@router.delete(
    "/{organization_id}",
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def delete_aoao_organization(organization_id: str):
    """
    Delete an AOAO organization.
    
    Admin only.
    """
    client = get_supabase_client()
    
    try:
        result = (
            client.table("aoao_organizations")
            .delete()
            .eq("id", organization_id)
            .execute()
        )
        
        return {"success": True, "message": "AOAO organization deleted"}
    except Exception as e:
        handle_supabase_error(e, "Failed to delete AOAO organization")

