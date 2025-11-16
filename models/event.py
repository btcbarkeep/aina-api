from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from .enums import EventType


# -------------------------------------------------
# Shared Fields (used across Create/Read/Update)
# -------------------------------------------------
class EventBase(BaseModel):
    building_id: str
    unit_number: Optional[str] = None
    event_type: EventType
    title: str
    body: Optional[str] = None
    occurred_at: datetime

    # NEW FIELDS (allowed in Create / Update)
    severity: Optional[str] = "medium"      # low, medium, high, urgent
    status: Optional[str] = "open"          # open, in_progress, resolved

    # contractor_id is optional during create
    contractor_id: Optional[str] = None


# -------------------------------------------------
# Create Event
# -------------------------------------------------
class EventCreate(EventBase):
    """
    Client sends this when creating an event.
    - Supabase will generate id and created_at
    - created_by is injected by backend (not provided by client)
    """
    pass


# -------------------------------------------------
# Read Event (returned from Supabase)
# -------------------------------------------------
class EventRead(EventBase):
    id: str
    created_at: datetime

    # NEW in read model
    created_by: Optional[str] = None


# -------------------------------------------------
# Update Event (partial)
# -------------------------------------------------
class EventUpdate(BaseModel):
    building_id: Optional[str] = None
    unit_number: Optional[str] = None
    event_type: Optional[EventType] = None
    title: Optional[str] = None
    body: Optional[str] = None
    occurred_at: Optional[datetime] = None

    # NEW — admin/manager can update these
    severity: Optional[str] = None
    status: Optional[str] = None
    contractor_id: Optional[str] = None
