# models/message.py

from typing import Optional
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


class MessageRead(MessageBase):
    """Read message model."""
    id: str
    from_user_id: str
    to_user_id: Optional[str] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

