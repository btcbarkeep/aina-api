# routers/subscriptions.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client
from core.logging_config import logger
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
from models.subscription import UserSubscriptionRead, UserSubscriptionCreate, UserSubscriptionUpdate
from models.enums import SubscriptionTier, SubscriptionStatus

router = APIRouter(
    prefix="/subscriptions",
    tags=["Subscriptions"],
)


@router.get("/me", response_model=List[UserSubscriptionRead])
def get_my_subscriptions(
    role: Optional[str] = Query(None, description="Filter by role"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get all subscriptions for the current user.
    
    Optionally filter by role.
    """
    subscriptions = get_user_subscriptions(current_user.auth_user_id)
    
    if role:
        subscriptions = [s for s in subscriptions if s.get("role") == role]
    
    return subscriptions


@router.get("/me/{role}", response_model=UserSubscriptionRead)
def get_my_subscription_by_role(
    role: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get subscription for the current user's specific role.
    """
    subscription = get_user_subscription(current_user.auth_user_id, role)
    
    if not subscription:
        raise HTTPException(404, f"No subscription found for role '{role}'")
    
    return subscription


@router.post("/me/{role}/sync", response_model=UserSubscriptionRead)
def sync_my_subscription(
    role: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Manually sync subscription status from Stripe for the current user's role.
    
    This endpoint:
    1. Verifies the subscription status with Stripe
    2. Updates the user's subscription record
    3. Returns the updated subscription data
    """
    subscription = get_user_subscription(current_user.auth_user_id, role)
    
    if not subscription:
        raise HTTPException(404, f"No subscription found for role '{role}'")
    
    stripe_customer_id = subscription.get("stripe_customer_id")
    stripe_subscription_id = subscription.get("stripe_subscription_id")
    
    if not stripe_customer_id and not stripe_subscription_id:
        raise HTTPException(
            400,
            f"Subscription for role '{role}' does not have a Stripe customer ID or subscription ID. Cannot sync."
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
    trial_days: int = Query(14, ge=1, le=180, description="Trial duration in days (1-180)"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Start a free trial for the current user's role.
    
    Automatically uses the current user's role (from their authentication).
    
    **Requirements:**
    - Role must support trials (AOAO, property_manager, contractor, owner)
    - User must not already have an active subscription for this role
    
    **Note:** AOAO role requires paid subscription after trial expires.
    """
    # Use the current user's role
    role = current_user.role
    
    if not role:
        raise HTTPException(400, "User does not have a role assigned")
    
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

