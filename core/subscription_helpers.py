# core/subscription_helpers.py

"""
Helper functions for fetching and managing user subscriptions.
"""

from typing import Optional, Dict, Any
from datetime import datetime
from core.supabase_client import get_supabase_client
from core.logging_config import logger


def get_user_subscription(user_id: str, role: str) -> Optional[Dict[str, Any]]:
    """
    Fetch user subscription for a specific role.
    
    Args:
        user_id: User ID (UUID)
        role: User role
    
    Returns:
        Subscription dictionary or None if not found
    """
    client = get_supabase_client()
    
    try:
        result = (
            client.table("user_subscriptions")
            .select("*")
            .eq("user_id", user_id)
            .eq("role", role)
            .limit(1)
            .execute()
        )
        
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Error fetching subscription for user {user_id}, role {role}: {e}")
        return None


def get_user_subscriptions(user_id: str) -> list[Dict[str, Any]]:
    """
    Fetch all subscriptions for a user.
    
    Args:
        user_id: User ID (UUID)
    
    Returns:
        List of subscription dictionaries
    """
    client = get_supabase_client()
    
    try:
        result = (
            client.table("user_subscriptions")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        
        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching subscriptions for user {user_id}: {e}")
        return []


def create_or_update_user_subscription(
    user_id: str,
    role: str,
    subscription_tier: str = "free",
    subscription_status: Optional[str] = None,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
    is_trial: bool = False,
    trial_started_at: Optional[datetime] = None,
    trial_ends_at: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Create or update a user subscription.
    
    Uses UPSERT to handle both create and update cases.
    
    Args:
        user_id: User ID (UUID)
        role: User role
        subscription_tier: "free" or "paid"
        subscription_status: Stripe subscription status
        stripe_customer_id: Stripe customer ID
        stripe_subscription_id: Stripe subscription ID
        is_trial: Whether subscription is in trial
        trial_started_at: When trial started
        trial_ends_at: When trial ends
    
    Returns:
        Created/updated subscription dictionary
    """
    client = get_supabase_client()
    
    subscription_data = {
        "user_id": user_id,
        "role": role,
        "subscription_tier": subscription_tier,
        "subscription_status": subscription_status,
        "stripe_customer_id": stripe_customer_id,
        "stripe_subscription_id": stripe_subscription_id,
        "is_trial": is_trial,
        "trial_started_at": trial_started_at.isoformat() if trial_started_at else None,
        "trial_ends_at": trial_ends_at.isoformat() if trial_ends_at else None,
    }
    
    # Remove None values
    subscription_data = {k: v for k, v in subscription_data.items() if v is not None}
    
    try:
        # Use upsert (insert with conflict resolution)
        result = (
            client.table("user_subscriptions")
            .upsert(
                subscription_data,
                on_conflict="user_id,role"
            )
            .execute()
        )
        
        if result.data:
            return result.data[0]
        raise Exception("Upsert returned no data")
    except Exception as e:
        logger.error(f"Error creating/updating subscription for user {user_id}, role {role}: {e}")
        raise

