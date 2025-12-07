# models/subscription.py

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from models.enums import SubscriptionTier, SubscriptionStatus


class UserSubscriptionBase(BaseModel):
    """Base subscription model."""
    role: str = Field(..., description="User role this subscription applies to")
    subscription_tier: SubscriptionTier = Field(SubscriptionTier.free, description="Subscription tier: 'free' or 'paid'")
    subscription_status: Optional[SubscriptionStatus] = Field(None, description="Stripe subscription status")
    stripe_customer_id: Optional[str] = Field(None, description="Stripe customer ID")
    stripe_subscription_id: Optional[str] = Field(None, description="Stripe subscription ID")
    is_trial: bool = Field(False, description="Whether subscription is in trial period")
    trial_started_at: Optional[datetime] = Field(None, description="When trial period started")
    trial_ends_at: Optional[datetime] = Field(None, description="When trial period ends")


class UserSubscriptionCreate(UserSubscriptionBase):
    """Create subscription model."""
    user_id: str = Field(..., description="User ID (UUID)")


class UserSubscriptionUpdate(BaseModel):
    """Update subscription model - all fields optional."""
    subscription_tier: Optional[SubscriptionTier] = None
    subscription_status: Optional[SubscriptionStatus] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    is_trial: Optional[bool] = None
    trial_started_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None


class UserSubscriptionRead(UserSubscriptionBase):
    """Read subscription model."""
    id: str
    user_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}

