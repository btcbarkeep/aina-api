# models/access_request.py

from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field


RequestType = Literal["building", "unit"]
RequestStatus = Literal["pending", "approved", "rejected"]
OrganizationType = Literal["pm_company", "aoao_organization"]


class AccessRequestBase(BaseModel):
    """Base access request model."""
    request_type: RequestType = Field(..., description="Type of request: 'building' or 'unit'")
    building_id: Optional[str] = Field(None, description="Building ID (required for building requests)")
    unit_id: Optional[str] = Field(None, description="Unit ID (required for unit requests)")
    organization_type: Optional[OrganizationType] = Field(None, description="Type of organization (if applicable)")
    organization_id: Optional[str] = Field(None, description="PM company or AOAO organization ID (if applicable)")
    notes: Optional[str] = Field(None, description="Request notes/justification")


class AccessRequestCreate(AccessRequestBase):
    """Create access request model."""
    pass


class AccessRequestUpdate(BaseModel):
    """Update access request model (admin only)."""
    status: Optional[RequestStatus] = None
    admin_notes: Optional[str] = Field(None, description="Admin-only notes")


class AccessRequestRead(AccessRequestBase):
    """Read access request model."""
    id: str
    requester_user_id: str
    status: RequestStatus
    admin_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

