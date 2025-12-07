# routers/subscriptions.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client
from core.logging_config import logger
from core.config import settings
from core.subscription_helpers import (
    get_user_subscription,
    get_user_subscriptions,
    create_or_update_user_subscription
)
from core.role_subscriptions import (
    validate_role_subscription,
    get_role_subscription_requirements,
    is_trial_active
)
from core.stripe_helpers import verify_contractor_subscription
from models.subscription import UserSubscriptionRead
from models.enums import SubscriptionTier, SubscriptionStatus

router = APIRouter(
    prefix="/subscriptions",
    tags=["Subscriptions"],
)


@router.get("/me", response_model=UserSubscriptionRead)
def get_my_subscription(
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get subscription for the current user.
    
    Since users have a single role, this returns their subscription for that role.
    """
    role = current_user.role
    
    if not role:
        raise HTTPException(400, "User does not have a role assigned")
    
    subscription = get_user_subscription(current_user.auth_user_id, role)
    
    if not subscription:
        raise HTTPException(404, f"No subscription found for role '{role}'")
    
    return subscription


@router.post("/me/sync", response_model=UserSubscriptionRead)
def sync_my_subscription(
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Manually sync subscription status from Stripe for the current user.
    
    Automatically uses the current user's role. This endpoint:
    1. Verifies the subscription status with Stripe
    2. Updates the user's subscription record
    3. Returns the updated subscription data
    """
    role = current_user.role
    
    if not role:
        raise HTTPException(400, "User does not have a role assigned")
    
    subscription = get_user_subscription(current_user.auth_user_id, role)
    
    if not subscription:
        raise HTTPException(404, f"No subscription found for role '{role}'")
    
    stripe_customer_id = subscription.get("stripe_customer_id")
    stripe_subscription_id = subscription.get("stripe_subscription_id")
    
    if not stripe_customer_id and not stripe_subscription_id:
        raise HTTPException(
            400,
            f"Subscription does not have a Stripe customer ID or subscription ID. Cannot sync."
        )
    
    # Verify subscription with Stripe
    is_active, subscription_status, error_message = verify_contractor_subscription(
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id
    )
    
    if error_message:
        logger.warning(f"Error syncing subscription for user {current_user.auth_user_id}, role {role}: {error_message}")
        raise HTTPException(400, f"Failed to verify subscription: {error_message}")
    
    # Determine subscription tier
    subscription_tier = "paid" if is_active else "free"
    
    # Check if trial is still active
    is_trial = subscription.get("is_trial", False)
    trial_ends_at = subscription.get("trial_ends_at")
    if trial_ends_at:
        trial_ends_at = datetime.fromisoformat(trial_ends_at.replace('Z', '+00:00'))
        if not is_trial_active(trial_ends_at):
            is_trial = False
    
    # Update subscription
    updated_subscription = create_or_update_user_subscription(
        user_id=current_user.auth_user_id,
        role=role,
        subscription_tier=subscription_tier,
        subscription_status=subscription_status,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        is_trial=is_trial,
        trial_started_at=subscription.get("trial_started_at"),
        trial_ends_at=trial_ends_at
    )
    
    logger.info(
        f"Synced subscription for user {current_user.auth_user_id}, role {role}: "
        f"tier={subscription_tier}, status={subscription_status}"
    )
    
    return updated_subscription


@router.post("/me/start-trial", response_model=UserSubscriptionRead)
def start_trial(
    trial_days: Optional[int] = Query(
        None,
        ge=1,
        description=f"Trial duration in days ({settings.TRIAL_SELF_SERVICE_MIN_DAYS}-{settings.TRIAL_SELF_SERVICE_MAX_DAYS}). Defaults to {settings.TRIAL_SELF_SERVICE_MAX_DAYS} days if not specified."
    ),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Start a free trial for the CURRENT USER ONLY (per-user subscription).
    
    This creates a subscription record specifically for the authenticated user.
    It does NOT affect other users with the same role.
    
    **How it works:**
    - Automatically uses the current user's role (from their authentication token)
    - Creates a subscription record in `user_subscriptions` table for THIS USER ONLY
    - Each user has their own independent subscription
    
    **Requirements:**
    - Role must support trials (AOAO, property_manager, contractor, owner)
    - User must not already have an active subscription for this role
    
    **Note:** AOAO role requires paid subscription after trial expires.
    """
    # Use the current user's role
    role = current_user.role
    
    if not role:
        raise HTTPException(400, "User does not have a role assigned")
    
    # Apply self-service trial limits
    if trial_days is None:
        trial_days = settings.TRIAL_SELF_SERVICE_MAX_DAYS
    
    if trial_days < settings.TRIAL_SELF_SERVICE_MIN_DAYS:
        raise HTTPException(
            400,
            f"Trial duration must be at least {settings.TRIAL_SELF_SERVICE_MIN_DAYS} days for self-service trials"
        )
    
    if trial_days > settings.TRIAL_SELF_SERVICE_MAX_DAYS:
        raise HTTPException(
            400,
            f"Trial duration cannot exceed {settings.TRIAL_SELF_SERVICE_MAX_DAYS} days for self-service trials. "
            f"Please contact an admin for longer trials."
        )
    
    requirements = get_role_subscription_requirements(role)
    
    if not requirements["supports_trial"]:
        raise HTTPException(400, f"Role '{role}' does not support free trials")
    
    # Check if subscription already exists
    existing = get_user_subscription(current_user.auth_user_id, role)
    
    if existing:
        # Check if already has active paid subscription
        if existing.get("subscription_tier") == "paid" and existing.get("subscription_status") in ["active", "trialing"]:
            raise HTTPException(400, f"User already has an active paid subscription for role '{role}'")
        
        # Check if trial is already active
        if existing.get("is_trial") and existing.get("trial_ends_at"):
            trial_ends_at = datetime.fromisoformat(existing.get("trial_ends_at").replace('Z', '+00:00'))
            if is_trial_active(trial_ends_at):
                raise HTTPException(400, f"User already has an active trial for role '{role}'")
        
        # Prevent multiple self-service trials (even after expiration)
        # Users who have already used a trial cannot start another one via self-service
        # Admins can still grant trials via the admin endpoint
        if existing.get("is_trial") or existing.get("trial_started_at"):
            raise HTTPException(
                400,
                f"User has already used a free trial for role '{role}'. "
                f"Please contact an admin if you need another trial."
            )
    
    # Start trial
    now = datetime.now(timezone.utc)
    trial_ends_at = now + timedelta(days=trial_days)
    
    subscription = create_or_update_user_subscription(
        user_id=current_user.auth_user_id,
        role=role,
        subscription_tier="paid" if requirements["requires_paid"] else "free",
        subscription_status="trialing",
        is_trial=True,
        trial_started_at=now,
        trial_ends_at=trial_ends_at
    )
    
    logger.info(
        f"Started {trial_days}-day trial for user {current_user.auth_user_id}, role {role}. "
        f"Trial ends at {trial_ends_at.isoformat()}"
    )
    
    return subscription


# Admin endpoints (for managing user subscriptions)
@router.get("/users/{user_id}", response_model=List[UserSubscriptionRead])
def get_user_subscriptions_admin(
    user_id: str,
    role: Optional[str] = Query(None, description="Filter by role"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get all subscriptions for a user (admin only).
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admins can view other users' subscriptions")
    
    subscriptions = get_user_subscriptions(user_id)
    
    if role:
        subscriptions = [s for s in subscriptions if s.get("role") == role]
    
    return subscriptions


@router.post("/users/{user_id}/start-trial", response_model=UserSubscriptionRead)
def admin_start_trial_for_user(
    user_id: str,
    role: Optional[str] = Query(None, description="Role to start trial for (defaults to user's current role from their metadata)"),
    trial_days: Optional[int] = Query(
        None,
        ge=1,
        description=f"Trial duration in days ({settings.TRIAL_ADMIN_MIN_DAYS}-{settings.TRIAL_ADMIN_MAX_DAYS}). Defaults to {settings.TRIAL_ADMIN_MAX_DAYS} days if not specified."
    ),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Admin: Grant a free trial to a specific user.
    
    **Admin Only:** Only admins and super_admins can grant trials to users.
    
    **How it works:**
    - Creates a subscription record for the specified user
    - If `role` is not provided, automatically fetches the user's role from their metadata
    - Each user has their own independent subscription
    
    **Requirements:**
    - Role must support trials (AOAO, property_manager, contractor, owner)
    - User must not already have an active subscription for this role
    
    **Note:** AOAO role requires paid subscription after trial expires.
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admins can grant trials to users")
    
    # Get the target user's role if not provided
    if not role:
        client = get_supabase_client()
        try:
            # Fetch user from Supabase auth to get their role
            resp = client.auth.admin.get_user_by_id(user_id)
            if not resp.user:
                # Check if this might be a contractor ID instead
                contractor_check = (
                    client.table("contractors")
                    .select("id, company_name")
                    .eq("id", user_id)
                    .limit(1)
                    .execute()
                )
                if contractor_check.data:
                    contractor = contractor_check.data[0]
                    # Try to find users linked to this contractor
                    try:
                        # Note: We can't directly query auth.users, but we can check if there are any users
                        # with this contractor_id in their metadata via a custom query if needed
                        raise HTTPException(
                            400,
                            f"'{user_id}' is a contractor ID (company: {contractor.get('company_name', 'Unknown')}), not a user ID. "
                            f"Please use a user ID from auth.users. To grant a trial to a contractor user, you need their user account ID (from auth.users), not the contractor company ID. "
                            f"Use GET /admin/users to find users linked to this contractor."
                        )
                    except HTTPException:
                        raise
                raise HTTPException(404, f"User {user_id} not found in auth.users")
            
            metadata = resp.user.user_metadata or {}
            role = metadata.get("role", "aoao")
            
            if not role:
                raise HTTPException(400, f"User {user_id} does not have a role assigned. Please specify the role parameter.")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching user {user_id} for trial: {e}")
            # Check if this might be a contractor ID
            try:
                contractor_check = (
                    client.table("contractors")
                    .select("id, company_name")
                    .eq("id", user_id)
                    .limit(1)
                    .execute()
                )
                if contractor_check.data:
                    contractor = contractor_check.data[0]
                    raise HTTPException(
                        400,
                        f"'{user_id}' is a contractor ID (company: {contractor.get('company_name', 'Unknown')}), not a user ID. "
                        f"Please use a user ID from auth.users."
                    )
            except HTTPException:
                raise
            raise HTTPException(500, f"Failed to fetch user information: {str(e)}")
    
    # Apply admin trial limits
    if trial_days is None:
        trial_days = settings.TRIAL_ADMIN_MAX_DAYS
    
    if trial_days < settings.TRIAL_ADMIN_MIN_DAYS:
        raise HTTPException(
            400,
            f"Trial duration must be at least {settings.TRIAL_ADMIN_MIN_DAYS} days"
        )
    
    if trial_days > settings.TRIAL_ADMIN_MAX_DAYS:
        raise HTTPException(
            400,
            f"Trial duration cannot exceed {settings.TRIAL_ADMIN_MAX_DAYS} days"
        )
    
    requirements = get_role_subscription_requirements(role)
    
    if not requirements["supports_trial"]:
        raise HTTPException(400, f"Role '{role}' does not support free trials")
    
    # Check if subscription already exists
    existing = get_user_subscription(user_id, role)
    
    if existing:
        # Check if already has active paid subscription
        if existing.get("subscription_tier") == "paid" and existing.get("subscription_status") in ["active", "trialing"]:
            raise HTTPException(400, f"User already has an active paid subscription for role '{role}'")
        
        # Check if trial is already active
        if existing.get("is_trial") and existing.get("trial_ends_at"):
            trial_ends_at = datetime.fromisoformat(existing.get("trial_ends_at").replace('Z', '+00:00'))
            if is_trial_active(trial_ends_at):
                raise HTTPException(400, f"User already has an active trial for role '{role}'")
    
    # Start trial
    now = datetime.now(timezone.utc)
    trial_ends_at = now + timedelta(days=trial_days)
    
    subscription = create_or_update_user_subscription(
        user_id=user_id,
        role=role,
        subscription_tier="paid" if requirements["requires_paid"] else "free",
        subscription_status="trialing",
        is_trial=True,
        trial_started_at=now,
        trial_ends_at=trial_ends_at
    )
    
    logger.info(
        f"Admin {current_user.auth_user_id} granted {trial_days}-day trial to user {user_id}, role {role}. "
        f"Trial ends at {trial_ends_at.isoformat()}"
    )
    
    return subscription


# ============================================================
# BUSINESS TRIAL ENDPOINTS (Contractors, AOAO Orgs, PM Companies)
# ============================================================

@router.post("/contractors/{contractor_id}/start-trial")
def start_contractor_trial(
    contractor_id: str,
    trial_days: Optional[int] = Query(
        None,
        ge=1,
        description=f"Trial duration in days ({settings.TRIAL_ADMIN_MIN_DAYS}-{settings.TRIAL_ADMIN_MAX_DAYS}). Defaults to {settings.TRIAL_ADMIN_MAX_DAYS} days if not specified."
    ),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Admin: Grant a free trial to a contractor company.
    
    **Admin Only:** Only admins and super_admins can grant trials.
    
    Updates the contractor's subscription to "trialing" status.
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admins can grant trials to contractors")
    
    # Apply admin trial limits
    if trial_days is None:
        trial_days = settings.TRIAL_ADMIN_MAX_DAYS
    
    if trial_days < settings.TRIAL_ADMIN_MIN_DAYS:
        raise HTTPException(400, f"Trial duration must be at least {settings.TRIAL_ADMIN_MIN_DAYS} days")
    
    if trial_days > settings.TRIAL_ADMIN_MAX_DAYS:
        raise HTTPException(400, f"Trial duration cannot exceed {settings.TRIAL_ADMIN_MAX_DAYS} days")
    
    client = get_supabase_client()
    
    # Check if contractor exists
    contractor = (
        client.table("contractors")
        .select("id, company_name, subscription_tier, subscription_status")
        .eq("id", contractor_id)
        .limit(1)
        .execute()
    )
    
    if not contractor.data:
        raise HTTPException(404, f"Contractor {contractor_id} not found")
    
    contractor_data = contractor.data[0]
    
    # Check if already has active subscription
    if contractor_data.get("subscription_tier") == "paid" and contractor_data.get("subscription_status") in ["active", "trialing"]:
        raise HTTPException(400, f"Contractor already has an active paid subscription")
    
    # Update contractor subscription
    try:
        update_res = (
            client.table("contractors")
            .update({
                "subscription_tier": "paid",
                "subscription_status": "trialing"
            })
            .eq("id", contractor_id)
            .execute()
        )
        
        if not update_res.data:
            raise HTTPException(500, "Failed to update contractor subscription")
        
        logger.info(
            f"Admin {current_user.auth_user_id} granted {trial_days}-day trial to contractor {contractor_id} "
            f"({contractor_data.get('company_name', 'Unknown')})"
        )
        
        return {
            "success": True,
            "contractor_id": contractor_id,
            "company_name": contractor_data.get("company_name"),
            "subscription_tier": "paid",
            "subscription_status": "trialing",
            "trial_days": trial_days
        }
    except Exception as e:
        logger.error(f"Error granting trial to contractor {contractor_id}: {e}")
        raise HTTPException(500, f"Failed to grant trial: {str(e)}")


@router.post("/aoao-organizations/{organization_id}/start-trial")
def start_aoao_org_trial(
    organization_id: str,
    trial_days: Optional[int] = Query(
        None,
        ge=1,
        description=f"Trial duration in days ({settings.TRIAL_ADMIN_MIN_DAYS}-{settings.TRIAL_ADMIN_MAX_DAYS}). Defaults to {settings.TRIAL_ADMIN_MAX_DAYS} days if not specified."
    ),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Admin: Grant a free trial to an AOAO organization.
    
    **Admin Only:** Only admins and super_admins can grant trials.
    
    Updates the organization's subscription to "trialing" status.
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admins can grant trials to AOAO organizations")
    
    # Apply admin trial limits
    if trial_days is None:
        trial_days = settings.TRIAL_ADMIN_MAX_DAYS
    
    if trial_days < settings.TRIAL_ADMIN_MIN_DAYS:
        raise HTTPException(400, f"Trial duration must be at least {settings.TRIAL_ADMIN_MIN_DAYS} days")
    
    if trial_days > settings.TRIAL_ADMIN_MAX_DAYS:
        raise HTTPException(400, f"Trial duration cannot exceed {settings.TRIAL_ADMIN_MAX_DAYS} days")
    
    client = get_supabase_client()
    
    # Check if organization exists
    org = (
        client.table("aoao_organizations")
        .select("id, organization_name, subscription_tier, subscription_status")
        .eq("id", organization_id)
        .limit(1)
        .execute()
    )
    
    if not org.data:
        raise HTTPException(404, f"AOAO organization {organization_id} not found")
    
    org_data = org.data[0]
    
    # Check if already has active subscription
    if org_data.get("subscription_tier") == "paid" and org_data.get("subscription_status") in ["active", "trialing"]:
        raise HTTPException(400, f"AOAO organization already has an active paid subscription")
    
    # Update organization subscription
    try:
        update_res = (
            client.table("aoao_organizations")
            .update({
                "subscription_tier": "paid",
                "subscription_status": "trialing"
            })
            .eq("id", organization_id)
            .execute()
        )
        
        if not update_res.data:
            raise HTTPException(500, "Failed to update AOAO organization subscription")
        
        logger.info(
            f"Admin {current_user.auth_user_id} granted {trial_days}-day trial to AOAO organization {organization_id} "
            f"({org_data.get('organization_name', 'Unknown')})"
        )
        
        return {
            "success": True,
            "organization_id": organization_id,
            "organization_name": org_data.get("organization_name"),
            "subscription_tier": "paid",
            "subscription_status": "trialing",
            "trial_days": trial_days
        }
    except Exception as e:
        logger.error(f"Error granting trial to AOAO organization {organization_id}: {e}")
        raise HTTPException(500, f"Failed to grant trial: {str(e)}")


@router.post("/pm-companies/{company_id}/start-trial")
def start_pm_company_trial(
    company_id: str,
    trial_days: Optional[int] = Query(
        None,
        ge=1,
        description=f"Trial duration in days ({settings.TRIAL_ADMIN_MIN_DAYS}-{settings.TRIAL_ADMIN_MAX_DAYS}). Defaults to {settings.TRIAL_ADMIN_MAX_DAYS} days if not specified."
    ),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Admin: Grant a free trial to a property management company.
    
    **Admin Only:** Only admins and super_admins can grant trials.
    
    Updates the company's subscription to "trialing" status.
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admins can grant trials to property management companies")
    
    # Apply admin trial limits
    if trial_days is None:
        trial_days = settings.TRIAL_ADMIN_MAX_DAYS
    
    if trial_days < settings.TRIAL_ADMIN_MIN_DAYS:
        raise HTTPException(400, f"Trial duration must be at least {settings.TRIAL_ADMIN_MIN_DAYS} days")
    
    if trial_days > settings.TRIAL_ADMIN_MAX_DAYS:
        raise HTTPException(400, f"Trial duration cannot exceed {settings.TRIAL_ADMIN_MAX_DAYS} days")
    
    client = get_supabase_client()
    
    # Check if company exists
    company = (
        client.table("property_management_companies")
        .select("id, company_name, subscription_tier, subscription_status")
        .eq("id", company_id)
        .limit(1)
        .execute()
    )
    
    if not company.data:
        raise HTTPException(404, f"Property management company {company_id} not found")
    
    company_data = company.data[0]
    
    # Check if already has active subscription
    if company_data.get("subscription_tier") == "paid" and company_data.get("subscription_status") in ["active", "trialing"]:
        raise HTTPException(400, f"Property management company already has an active paid subscription")
    
    # Update company subscription
    try:
        update_res = (
            client.table("property_management_companies")
            .update({
                "subscription_tier": "paid",
                "subscription_status": "trialing"
            })
            .eq("id", company_id)
            .execute()
        )
        
        if not update_res.data:
            raise HTTPException(500, "Failed to update property management company subscription")
        
        logger.info(
            f"Admin {current_user.auth_user_id} granted {trial_days}-day trial to PM company {company_id} "
            f"({company_data.get('company_name', 'Unknown')})"
        )
        
        return {
            "success": True,
            "company_id": company_id,
            "company_name": company_data.get("company_name"),
            "subscription_tier": "paid",
            "subscription_status": "trialing",
            "trial_days": trial_days
        }
    except Exception as e:
        logger.error(f"Error granting trial to PM company {company_id}: {e}")
        raise HTTPException(500, f"Failed to grant trial: {str(e)}")


# ============================================================
# LIST ALL SUBSCRIPTIONS (Admin Only)
# ============================================================

@router.get("/all")
def list_all_subscriptions(
    subscription_tier: Optional[str] = Query(None, description="Filter by subscription tier (free, paid)"),
    subscription_status: Optional[str] = Query(None, description="Filter by subscription status (active, canceled, past_due, trialing, etc.)"),
    subscription_type: Optional[str] = Query(None, description="Filter by subscription type (user, contractor, aoao_organization, pm_company)"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    List all subscriptions across all types (users, contractors, AOAO organizations, PM companies).
    
    **Admin Only:** Only admins and super_admins can view all subscriptions.
    
    Returns a comprehensive list of all subscriptions with their details.
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admins can view all subscriptions")
    
    client = get_supabase_client()
    all_subscriptions = []
    
    try:
        # 1. Get all user subscriptions
        user_subscriptions_result = (
            client.table("user_subscriptions")
            .select("*")
            .execute()
        )
        
        for sub in (user_subscriptions_result.data or []):
            # Get user details
            try:
                user_resp = client.auth.admin.get_user_by_id(sub["user_id"])
                user_email = user_resp.user.email if user_resp.user else None
                user_metadata = user_resp.user.user_metadata or {} if user_resp.user else {}
                user_name = user_metadata.get("full_name") or user_email
            except:
                user_email = None
                user_name = f"User {sub['user_id']}"
            
            subscription_entry = {
                "subscription_type": "user",
                "id": sub["id"],
                "user_id": sub["user_id"],
                "user_email": user_email,
                "user_name": user_name,
                "role": sub.get("role"),
                "subscription_tier": sub.get("subscription_tier"),
                "subscription_status": sub.get("subscription_status"),
                "stripe_customer_id": sub.get("stripe_customer_id"),
                "stripe_subscription_id": sub.get("stripe_subscription_id"),
                "is_trial": sub.get("is_trial", False),
                "trial_started_at": sub.get("trial_started_at"),
                "trial_ends_at": sub.get("trial_ends_at"),
                "created_at": sub.get("created_at"),
                "updated_at": sub.get("updated_at"),
            }
            
            # Apply filters
            if subscription_tier and subscription_entry["subscription_tier"] != subscription_tier:
                continue
            if subscription_status and subscription_entry["subscription_status"] != subscription_status:
                continue
            if subscription_type and subscription_entry["subscription_type"] != subscription_type:
                continue
            
            all_subscriptions.append(subscription_entry)
        
        # 2. Get all contractor subscriptions
        # Note: contractors table may not have is_trial, trial_started_at, trial_ends_at columns
        contractors_result = (
            client.table("contractors")
            .select("id, company_name, subscription_tier, subscription_status, stripe_customer_id, stripe_subscription_id, created_at, updated_at")
            .execute()
        )
        
        for contractor in (contractors_result.data or []):
            # Check if subscription_status is "trialing" to determine if it's a trial
            subscription_status = contractor.get("subscription_status")
            is_trial = subscription_status == "trialing" if subscription_status else False
            
            # For business entities, use created_at as proxy for trial_started_at if trialing
            # Trial end date is not tracked in contractors table, so we'll leave it as None
            created_at_str = contractor.get("created_at")
            trial_started_at = created_at_str if is_trial else None
            
            subscription_entry = {
                "subscription_type": "contractor",
                "id": contractor["id"],
                "company_name": contractor.get("company_name"),
                "subscription_tier": contractor.get("subscription_tier"),
                "subscription_status": subscription_status,
                "stripe_customer_id": contractor.get("stripe_customer_id"),
                "stripe_subscription_id": contractor.get("stripe_subscription_id"),
                "is_trial": is_trial,
                "trial_started_at": trial_started_at,
                "trial_ends_at": None,  # Not tracked in contractors table
                "created_at": created_at_str,
                "updated_at": contractor.get("updated_at"),
            }
            
            # Apply filters
            if subscription_tier and subscription_entry["subscription_tier"] != subscription_tier:
                continue
            if subscription_status and subscription_entry["subscription_status"] != subscription_status:
                continue
            if subscription_type and subscription_entry["subscription_type"] != subscription_type:
                continue
            
            all_subscriptions.append(subscription_entry)
        
        # 3. Get all AOAO organization subscriptions
        # Note: aoao_organizations table doesn't have is_trial, trial_started_at, trial_ends_at columns
        aoao_orgs_result = (
            client.table("aoao_organizations")
            .select("id, organization_name, subscription_tier, subscription_status, stripe_customer_id, stripe_subscription_id, created_at, updated_at")
            .execute()
        )
        
        for org in (aoao_orgs_result.data or []):
            # Check if subscription_status is "trialing" to determine if it's a trial
            subscription_status = org.get("subscription_status")
            is_trial = subscription_status == "trialing" if subscription_status else False
            
            # For business entities, use created_at as proxy for trial_started_at if trialing
            # Trial end date is not tracked in aoao_organizations table, so we'll leave it as None
            created_at_str = org.get("created_at")
            trial_started_at = created_at_str if is_trial else None
            
            subscription_entry = {
                "subscription_type": "aoao_organization",
                "id": org["id"],
                "organization_name": org.get("organization_name"),
                "subscription_tier": org.get("subscription_tier"),
                "subscription_status": subscription_status,
                "stripe_customer_id": org.get("stripe_customer_id"),
                "stripe_subscription_id": org.get("stripe_subscription_id"),
                "is_trial": is_trial,
                "trial_started_at": trial_started_at,
                "trial_ends_at": None,  # Not tracked in aoao_organizations table
                "created_at": created_at_str,
                "updated_at": org.get("updated_at"),
            }
            
            # Apply filters
            if subscription_tier and subscription_entry["subscription_tier"] != subscription_tier:
                continue
            if subscription_status and subscription_entry["subscription_status"] != subscription_status:
                continue
            if subscription_type and subscription_entry["subscription_type"] != subscription_type:
                continue
            
            all_subscriptions.append(subscription_entry)
        
        # 4. Get all PM company subscriptions
        # Note: property_management_companies table doesn't have is_trial, trial_started_at, trial_ends_at columns
        pm_companies_result = (
            client.table("property_management_companies")
            .select("id, company_name, subscription_tier, subscription_status, stripe_customer_id, stripe_subscription_id, created_at, updated_at")
            .execute()
        )
        
        for company in (pm_companies_result.data or []):
            # Check if subscription_status is "trialing" to determine if it's a trial
            subscription_status = company.get("subscription_status")
            is_trial = subscription_status == "trialing" if subscription_status else False
            
            # For business entities, use created_at as proxy for trial_started_at if trialing
            # Trial end date is not tracked in property_management_companies table, so we'll leave it as None
            created_at_str = company.get("created_at")
            trial_started_at = created_at_str if is_trial else None
            
            subscription_entry = {
                "subscription_type": "pm_company",
                "id": company["id"],
                "company_name": company.get("company_name"),
                "subscription_tier": company.get("subscription_tier"),
                "subscription_status": subscription_status,
                "stripe_customer_id": company.get("stripe_customer_id"),
                "stripe_subscription_id": company.get("stripe_subscription_id"),
                "is_trial": is_trial,
                "trial_started_at": trial_started_at,
                "trial_ends_at": None,  # Not tracked in property_management_companies table
                "created_at": created_at_str,
                "updated_at": company.get("updated_at"),
            }
            
            # Apply filters
            if subscription_tier and subscription_entry["subscription_tier"] != subscription_tier:
                continue
            if subscription_status and subscription_entry["subscription_status"] != subscription_status:
                continue
            if subscription_type and subscription_entry["subscription_type"] != subscription_type:
                continue
            
            all_subscriptions.append(subscription_entry)
        
        # Sort by created_at (newest first)
        all_subscriptions.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        
        return {
            "success": True,
            "total": len(all_subscriptions),
            "subscriptions": all_subscriptions
        }
        
    except Exception as e:
        logger.error(f"Error listing all subscriptions: {e}")
        raise HTTPException(500, f"Failed to list subscriptions: {str(e)}")

