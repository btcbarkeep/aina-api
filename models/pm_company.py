# models/pm_company.py

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from models.enums import SubscriptionTier, SubscriptionStatus


class PMCompanyBase(BaseModel):
    """Base property management company model."""
    company_name: str = Field(..., description="Company name (required, unique)")
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    
    # Subscription fields
    subscription_tier: SubscriptionTier = Field(SubscriptionTier.free, description="Subscription tier: 'free' or 'paid'")
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_status: Optional[SubscriptionStatus] = None


class PMCompanyCreate(PMCompanyBase):
    """Create PM company model."""
    pass


class PMCompanyUpdate(BaseModel):
    """Update PM company model - all fields optional."""
    company_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    subscription_tier: Optional[SubscriptionTier] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_status: Optional[SubscriptionStatus] = None


class PMCompanyRead(PMCompanyBase):
    """Read PM company model."""
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}

