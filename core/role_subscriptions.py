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
    trial_ends_at: Optional[datetime] = None
) -> bool:
    """
    Check if a user has an active subscription for their role.
    
    This is a convenience function that validates subscription status.
    
    Args:
        role: User role
        subscription_tier: "free" or "paid"
        subscription_status: Stripe subscription status
        is_trial: Whether subscription is in trial
        trial_ends_at: When trial ends
    
    Returns:
        True if user has active subscription, False otherwise
    """
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

