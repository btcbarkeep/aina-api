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
from core.stripe_helpers import verify_contractor_subscription

router = APIRouter(
    prefix="/aoao-organizations",
    tags=["AOAO Organizations"],
)


# ============================================================
# Helper — role-based access rules
# ============================================================
def ensure_aoao_org_access(current_user: CurrentUser, organization_id: str):
    """
    Admin, super_admin → full access
    AOAO user → only access their own organization
    """
    if current_user.role in ["admin", "super_admin"]:
        return
    
    if current_user.role == "aoao":
        user_org_id = getattr(current_user, "aoao_organization_id", None)
        if user_org_id == organization_id:
            return
    
    raise HTTPException(403, "Insufficient permissions")


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
    
    ensure_aoao_org_access(current_user, organization_id)
    
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


# ============================================================
# SYNC SUBSCRIPTION STATUS FROM STRIPE
# ============================================================
@router.post(
    "/{organization_id}/sync-subscription",
    summary="Sync subscription status from Stripe",
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def sync_aoao_org_subscription(
    organization_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Manually sync an AOAO organization's subscription status from Stripe.
    
    This endpoint:
    - Verifies the subscription status with Stripe
    - Updates the organization's subscription record
    - Returns the updated subscription data
    
    **Use cases:**
    - Manual sync when subscription changes
    - Troubleshooting subscription issues
    - Verifying subscription status after webhook delays
    """
    ensure_aoao_org_access(current_user, organization_id)
    
    client = get_supabase_client()
    
    # Get organization
    org_res = (
        client.table("aoao_organizations")
        .select("id, organization_name, stripe_customer_id, stripe_subscription_id, subscription_tier, subscription_status")
        .eq("id", organization_id)
        .limit(1)
        .execute()
    )
    
    if not org_res.data:
        raise HTTPException(404, "AOAO organization not found")
    
    org = org_res.data[0]
    stripe_customer_id = org.get("stripe_customer_id")
    stripe_subscription_id = org.get("stripe_subscription_id")
    
    if not stripe_customer_id and not stripe_subscription_id:
        raise HTTPException(
            400,
            "AOAO organization does not have a Stripe customer ID or subscription ID. Cannot sync subscription."
        )
    
    # Verify subscription with Stripe
    is_active, subscription_status, error_message = verify_contractor_subscription(
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id
    )
    
    if error_message:
        logger.warning(f"Error syncing subscription for AOAO organization {organization_id}: {error_message}")
        raise HTTPException(400, f"Failed to verify subscription: {error_message}")
    
    # Determine subscription tier
    subscription_tier = "paid" if is_active else "free"
    
    # Update organization
    try:
        update_res = (
            client.table("aoao_organizations")
            .update({
                "subscription_tier": subscription_tier,
                "subscription_status": subscription_status
            })
            .eq("id", organization_id)
            .execute()
        )
        
        if not update_res.data:
            raise HTTPException(500, "Failed to update AOAO organization subscription")
        
        logger.info(f"Synced subscription status for AOAO organization {organization_id}: tier={subscription_tier}, status={subscription_status}")
        
        return {
            "success": True,
            "organization_id": organization_id,
            "organization_name": org.get("organization_name"),
            "subscription_tier": subscription_tier,
            "subscription_status": subscription_status
        }
    except Exception as e:
        from core.errors import handle_supabase_error
        raise handle_supabase_error(e, "Failed to sync subscription status", 500)

