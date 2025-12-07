# core/role_subscriptions.py

"""
Role-based subscription requirements and validation.

Rules:
- AOAO role: Must be paid (but supports free trials)
- Other roles (property_manager, contractor, owner): Can have both free and paid tiers
"""

from typing import Optional, Dict
from datetime import datetime, timezone
from fastapi import HTTPException
from core.logging_config import logger


# ============================================================
# ROLE SUBSCRIPTION REQUIREMENTS
# ============================================================
ROLE_SUBSCRIPTION_REQUIREMENTS: Dict[str, Dict[str, any]] = {
    "aoao": {
        "requires_paid": True,  # AOAO role must be paid
        "supports_trial": True,  # But supports free trials
        "supports_free_tier": False,  # No permanent free tier
    },
    "aoao_staff": {
        "requires_paid": True,
        "supports_trial": True,
        "supports_free_tier": False,
    },
    "property_manager": {
        "requires_paid": False,  # Can be free or paid
        "supports_trial": True,
        "supports_free_tier": True,  # Supports permanent free tier
    },
    "contractor": {
        "requires_paid": False,
        "supports_trial": True,
        "supports_free_tier": True,
    },
    "contractor_staff": {
        "requires_paid": False,
        "supports_trial": True,
        "supports_free_tier": True,
    },
    "owner": {
        "requires_paid": False,
        "supports_trial": True,
        "supports_free_tier": True,
    },
    # Admin roles don't need subscriptions
    "admin": {
        "requires_paid": False,
        "supports_trial": False,
        "supports_free_tier": True,
    },
    "super_admin": {
        "requires_paid": False,
        "supports_trial": False,
        "supports_free_tier": True,
    },
}


def get_role_subscription_requirements(role: str) -> Dict[str, any]:
    """
    Get subscription requirements for a role.
    
    Args:
        role: User role name
    
    Returns:
        Dictionary with subscription requirements
    """
    return ROLE_SUBSCRIPTION_REQUIREMENTS.get(role, {
        "requires_paid": False,
        "supports_trial": False,
        "supports_free_tier": True,
    })


def is_trial_active(trial_ends_at: Optional[datetime]) -> bool:
    """
    Check if a trial is currently active.
    
    Args:
        trial_ends_at: Trial end datetime
    
    Returns:
        True if trial is active, False otherwise
    """
    if not trial_ends_at:
        return False
    
    now = datetime.now(timezone.utc)
    if isinstance(trial_ends_at, str):
        # Parse ISO format string
        try:
            trial_ends_at = datetime.fromisoformat(trial_ends_at.replace('Z', '+00:00'))
        except Exception:
            return False
    
    return now < trial_ends_at


def validate_role_subscription(
    role: str,
    subscription_tier: str,
    subscription_status: Optional[str] = None,
    is_trial: bool = False,
    trial_ends_at: Optional[datetime] = None,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None
) -> tuple[bool, Optional[str]]:
    """
    Validate that a user's subscription meets the requirements for their role.
    
    Args:
        role: User role
        subscription_tier: "free" or "paid"
        subscription_status: Stripe subscription status
        is_trial: Whether subscription is in trial
        trial_ends_at: When trial ends
        stripe_customer_id: Stripe customer ID
        stripe_subscription_id: Stripe subscription ID
    
    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])
    """
    requirements = get_role_subscription_requirements(role)
    
    # Admin roles don't need subscriptions
    if role in ["admin", "super_admin"]:
        return True, None
    
    # Check if role requires paid subscription
    if requirements["requires_paid"]:
        # AOAO role must be paid (or in trial)
        if subscription_tier == "free" and not is_trial:
            return False, f"Role '{role}' requires a paid subscription. Free tier is not available."
        
        # If in trial, check if trial is still active
        if is_trial:
            if not is_trial_active(trial_ends_at):
                return False, f"Trial period has expired for role '{role}'. A paid subscription is required."
        
        # If paid, verify subscription is active
        if subscription_tier == "paid":
            if subscription_status not in ["active", "trialing"]:
                return False, f"Paid subscription for role '{role}' is not active. Current status: {subscription_status or 'unknown'}"
    
    # For roles that support free tier, any tier is acceptable
    if requirements["supports_free_tier"]:
        # Free tier is always valid
        if subscription_tier == "free":
            return True, None
        
        # Paid tier should have active subscription
        if subscription_tier == "paid":
            if subscription_status not in ["active", "trialing"]:
                return False, f"Paid subscription for role '{role}' is not active. Current status: {subscription_status or 'unknown'}"
    
    return True, None


def check_user_has_active_subscription(
    role: str,
    subscription_tier: Optional[str] = None,
    subscription_status: Optional[str] = None,
    is_trial: Optional[bool] = None,
    trial_ends_at: Optional[datetime] = None,
    contractor_id: Optional[str] = None,
    aoao_organization_id: Optional[str] = None,
    pm_company_id: Optional[str] = None
) -> bool:
    """
    Check if a user has an active subscription for their role.
    
    For business users (contractor, aoao, property_manager), this checks BOTH:
    1. Organization/company subscription (from business tables) - takes precedence
    2. Individual user subscription (from user_subscriptions table) - fallback
    
    This is a convenience function that validates subscription status.
    
    Args:
        role: User role
        subscription_tier: "free" or "paid" (from user_subscriptions)
        subscription_status: Stripe subscription status (from user_subscriptions)
        is_trial: Whether subscription is in trial (from user_subscriptions)
        trial_ends_at: When trial ends (from user_subscriptions)
        contractor_id: Optional contractor ID to check company subscription
        aoao_organization_id: Optional AOAO organization ID to check organization subscription
        pm_company_id: Optional PM company ID to check company subscription
    
    Returns:
        True if user has active subscription, False otherwise
    """
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()
    
    # For contractor users, check company subscription first
    if role == "contractor" and contractor_id:
        try:
            contractor_res = (
                client.table("contractors")
                .select("subscription_tier, subscription_status")
                .eq("id", contractor_id)
                .limit(1)
                .execute()
            )
            
            if contractor_res.data:
                contractor = contractor_res.data[0]
                company_tier = contractor.get("subscription_tier", "free")
                company_status = contractor.get("subscription_status")
                
                # If company has paid subscription, user inherits access
                if company_tier == "paid" and company_status in ["active", "trialing"]:
                    return True
        except Exception:
            pass
    
    # For AOAO users, check organization subscription first
    if role == "aoao" and aoao_organization_id:
        try:
            org_res = (
                client.table("aoao_organizations")
                .select("subscription_tier, subscription_status")
                .eq("id", aoao_organization_id)
                .limit(1)
                .execute()
            )
            
            if org_res.data:
                org = org_res.data[0]
                org_tier = org.get("subscription_tier", "free")
                org_status = org.get("subscription_status")
                
                # If organization has paid subscription, user inherits access
                if org_tier == "paid" and org_status in ["active", "trialing"]:
                    return True
        except Exception:
            pass
    
    # For property_manager users, check PM company subscription first
    if role == "property_manager" and pm_company_id:
        try:
            pm_res = (
                client.table("property_management_companies")
                .select("subscription_tier, subscription_status")
                .eq("id", pm_company_id)
                .limit(1)
                .execute()
            )
            
            if pm_res.data:
                pm_company = pm_res.data[0]
                pm_tier = pm_company.get("subscription_tier", "free")
                pm_status = pm_company.get("subscription_status")
                
                # If company has paid subscription, user inherits access
                if pm_tier == "paid" and pm_status in ["active", "trialing"]:
                    return True
        except Exception:
            pass
    
    # Default to free tier if not specified
    if subscription_tier is None:
        subscription_tier = "free"
    
    is_valid, _ = validate_role_subscription(
        role=role,
        subscription_tier=subscription_tier,
        subscription_status=subscription_status,
        is_trial=is_trial or False,
        trial_ends_at=trial_ends_at
    )
    
    return is_valid

