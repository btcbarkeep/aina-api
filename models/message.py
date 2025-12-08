# models/message.py

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class MessageBase(BaseModel):
    """Base message model."""
    subject: str = Field(..., description="Message subject")
    body: str = Field(..., description="Message body/content")


class MessageCreate(MessageBase):
    """Create message model."""
    to_user_id: Optional[str] = Field(None, description="User ID to send message to (None = send to admins)")


class MessageUpdate(BaseModel):
    """Update message model - for marking as read."""
    is_read: Optional[bool] = None


class BulkMessageCreate(BaseModel):
    """Bulk message model for AOAO users and admins."""
    recipient_types: List[str] = Field(
        ..., 
        description="List of recipient types: 'contractors', 'property_managers', 'owners', 'aoao' (admins only). Can include multiple types."
    )
    subject: str = Field(..., description="Message subject")
    body: str = Field(..., description="Message body")
    building_id: Optional[str] = Field(
        None, 
        description="Optional: Filter recipients to those with access to this building. If not provided, uses all accessible buildings."
    )
    unit_id: Optional[str] = Field(
        None, 
        description="Optional: Filter recipients to those with access to this unit. If provided, building_id is ignored."
    )


class MessageRead(MessageBase):
    """Read message model."""
    id: str
    from_user_id: str
    to_user_id: Optional[str] = None
    is_read: bool
    read_at: Optional[datetime] = None
    replies_disabled: bool = Field(default=False, description="If true, only admins can reply (used for bulk announcements)")
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

