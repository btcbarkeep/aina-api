# models/premium_report_purchase.py

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID


class PremiumReportPurchaseBase(BaseModel):
    """Base model for premium report purchase."""
    customer_email: str = Field(..., description="Customer email address")
    customer_name: Optional[str] = Field(None, description="Customer name")
    report_type: str = Field(..., description="Type of report: building, unit, contractor, custom")
    report_id: Optional[str] = Field(None, description="ID of the generated report (if stored)")
    building_id: Optional[UUID] = Field(None, description="Building ID (if applicable)")
    unit_id: Optional[UUID] = Field(None, description="Unit ID (if applicable)")
    contractor_id: Optional[UUID] = Field(None, description="Contractor ID (if applicable)")
    stripe_session_id: Optional[str] = Field(None, description="Stripe Checkout Session ID")
    stripe_payment_intent_id: Optional[str] = Field(None, description="Stripe Payment Intent ID")
    stripe_customer_id: Optional[str] = Field(None, description="Stripe Customer ID")
    amount_cents: int = Field(..., description="Payment amount in cents")
    amount_decimal: float = Field(..., description="Payment amount in dollars")
    currency: str = Field(default="usd", description="Currency code")
    payment_status: str = Field(default="pending", description="Payment status: pending, paid, failed, refunded")


class PremiumReportPurchaseCreate(PremiumReportPurchaseBase):
    """Create model for premium report purchase."""
    pass


class PremiumReportPurchaseUpdate(BaseModel):
    """Update model for premium report purchase."""
    payment_status: Optional[str] = Field(None, description="Payment status: pending, paid, failed, refunded")
    report_id: Optional[str] = Field(None, description="ID of the generated report")


class PremiumReportPurchaseRead(PremiumReportPurchaseBase):
    """Read model for premium report purchase."""
    id: UUID
    purchased_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

