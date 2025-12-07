# routers/pm_companies.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from dependencies.auth import get_current_user, CurrentUser, requires_permission
from core.supabase_client import get_supabase_client
from core.utils import sanitize
from core.logging_config import logger
from core.errors import handle_supabase_error
from models.pm_company import (
    PMCompanyCreate,
    PMCompanyUpdate,
    PMCompanyRead
)
from models.enums import SubscriptionTier, SubscriptionStatus
from core.stripe_helpers import verify_contractor_subscription

router = APIRouter(
    prefix="/pm-companies",
    tags=["Property Management Companies"],
)


# ============================================================
# Helper — role-based access rules
# ============================================================
def ensure_pm_company_access(current_user: CurrentUser, company_id: str):
    """
    Admin, super_admin → full access
    Property manager → only access their own company
    """
    if current_user.role in ["admin", "super_admin"]:
        return
    
    if current_user.role == "property_manager":
        user_pm_id = getattr(current_user, "pm_company_id", None)
        if user_pm_id == company_id:
            return
    
    raise HTTPException(403, "Insufficient permissions")


# ============================================================
# LIST PM COMPANIES
# ============================================================
@router.get("", response_model=List[PMCompanyRead])
def list_pm_companies(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of companies to return (1-1000)"),
    search: Optional[str] = Query(None, description="Search companies by name (case-insensitive)"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    List all property management companies.
    
    Admin only.
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admins can list property management companies")
    
    client = get_supabase_client()
    query = client.table("property_management_companies").select("*")
    
    if search:
        query = query.ilike("company_name", f"%{search}%")
    
    query = query.order("company_name").limit(limit)
    result = query.execute()
    
    return result.data or []


# ============================================================
# GET PM COMPANY
# ============================================================
@router.get("/{company_id}", response_model=PMCompanyRead)
def get_pm_company(
    company_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get a specific property management company.
    
    Admin only, or users linked to this company.
    """
    client = get_supabase_client()
    
    ensure_pm_company_access(current_user, company_id)
    
    rows = (
        client.table("property_management_companies")
        .select("*")
        .eq("id", company_id)
        .limit(1)
        .execute()
    ).data
    
    if not rows:
        raise HTTPException(404, "Property management company not found")
    
    return rows[0]


# ============================================================
# CREATE PM COMPANY
# ============================================================
@router.post(
    "",
    response_model=PMCompanyRead,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def create_pm_company(payload: PMCompanyCreate):
    """
    Create a new property management company.
    
    Admin only.
    """
    client = get_supabase_client()
    
    # Check for duplicate company name (case-insensitive)
    company_name = payload.company_name.strip()
    existing = (
        client.table("property_management_companies")
        .select("id, company_name")
        .ilike("company_name", company_name)
        .limit(1)
        .execute()
    )
    
    if existing.data:
        raise HTTPException(
            400,
            f"Property management company with name '{company_name}' already exists. Company names must be unique."
        )
    
    # Prepare data
    data = sanitize(payload.model_dump())
    
    # Convert enum fields to strings for database
    if "subscription_tier" in data and data["subscription_tier"]:
        data["subscription_tier"] = str(data["subscription_tier"])
    if "subscription_status" in data and data["subscription_status"]:
        data["subscription_status"] = str(data["subscription_status"])
    
    try:
        insert_res = client.table("property_management_companies").insert(data).execute()
        if not insert_res.data:
            raise HTTPException(500, "Failed to create property management company")
        return insert_res.data[0]
    except Exception as e:
        handle_supabase_error(e, "Failed to create property management company")


# ============================================================
# UPDATE PM COMPANY
# ============================================================
@router.patch(
    "/{company_id}",
    response_model=PMCompanyRead,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def update_pm_company(
    company_id: str,
    payload: PMCompanyUpdate
):
    """
    Update a property management company.
    
    Admin only.
    """
    client = get_supabase_client()
    
    # Check if company exists
    existing = (
        client.table("property_management_companies")
        .select("id")
        .eq("id", company_id)
        .limit(1)
        .execute()
    )
    
    if not existing.data:
        raise HTTPException(404, "Property management company not found")
    
    # Check for duplicate name if updating
    if payload.company_name:
        company_name = payload.company_name.strip()
        duplicate = (
            client.table("property_management_companies")
            .select("id, company_name")
            .ilike("company_name", company_name)
            .neq("id", company_id)
            .limit(1)
            .execute()
        )
        
        if duplicate.data:
            raise HTTPException(
                400,
                f"Property management company with name '{company_name}' already exists."
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
            client.table("property_management_companies")
            .update(updates)
            .eq("id", company_id)
            .execute()
        )
        
        if not update_res.data:
            raise HTTPException(500, "Failed to update property management company")
        
        return update_res.data[0]
    except Exception as e:
        handle_supabase_error(e, "Failed to update property management company")


# ============================================================
# DELETE PM COMPANY
# ============================================================
@router.delete(
    "/{company_id}",
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def delete_pm_company(company_id: str):
    """
    Delete a property management company.
    
    Admin only.
    """
    client = get_supabase_client()
    
    try:
        result = (
            client.table("property_management_companies")
            .delete()
            .eq("id", company_id)
            .execute()
        )
        
        return {"success": True, "message": "Property management company deleted"}


# ============================================================
# SYNC SUBSCRIPTION STATUS FROM STRIPE
# ============================================================
@router.post(
    "/{company_id}/sync-subscription",
    summary="Sync subscription status from Stripe",
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def sync_pm_company_subscription(
    company_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Manually sync a property management company's subscription status from Stripe.
    
    This endpoint:
    - Verifies the subscription status with Stripe
    - Updates the company's subscription record
    - Returns the updated subscription data
    
    **Use cases:**
    - Manual sync when subscription changes
    - Troubleshooting subscription issues
    - Verifying subscription status after webhook delays
    """
    ensure_pm_company_access(current_user, company_id)
    
    client = get_supabase_client()
    
    # Get company
    company_res = (
        client.table("property_management_companies")
        .select("id, company_name, stripe_customer_id, stripe_subscription_id, subscription_tier, subscription_status")
        .eq("id", company_id)
        .limit(1)
        .execute()
    )
    
    if not company_res.data:
        raise HTTPException(404, "Property management company not found")
    
    company = company_res.data[0]
    stripe_customer_id = company.get("stripe_customer_id")
    stripe_subscription_id = company.get("stripe_subscription_id")
    
    if not stripe_customer_id and not stripe_subscription_id:
        raise HTTPException(
            400,
            "Property management company does not have a Stripe customer ID or subscription ID. Cannot sync subscription."
        )
    
    # Verify subscription with Stripe
    is_active, subscription_status, error_message = verify_contractor_subscription(
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id
    )
    
    if error_message:
        logger.warning(f"Error syncing subscription for PM company {company_id}: {error_message}")
        raise HTTPException(400, f"Failed to verify subscription: {error_message}")
    
    # Determine subscription tier
    subscription_tier = "paid" if is_active else "free"
    
    # Update company
    try:
        update_res = (
            client.table("property_management_companies")
            .update({
                "subscription_tier": subscription_tier,
                "subscription_status": subscription_status
            })
            .eq("id", company_id)
            .execute()
        )
        
        if not update_res.data:
            raise HTTPException(500, "Failed to update property management company subscription")
        
        logger.info(f"Synced subscription status for PM company {company_id}: tier={subscription_tier}, status={subscription_status}")
        
        return {
            "success": True,
            "company_id": company_id,
            "company_name": company.get("company_name"),
            "subscription_tier": subscription_tier,
            "subscription_status": subscription_status
        }
    except Exception as e:
        raise handle_supabase_error(e, "Failed to sync subscription status", 500)
    except Exception as e:
        handle_supabase_error(e, "Failed to delete property management company")

