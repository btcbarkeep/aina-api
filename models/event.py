from datetime import datetime
from typing import Optional
from pydantic import BaseModel, validator

from .enums import EventType, EventSeverity, EventStatus


# -------------------------------------------------
# Shared Fields
# -------------------------------------------------
class EventBase(BaseModel):
    building_id: str
    unit_number: Optional[str] = None
    event_type: EventType
    title: str
    body: Optional[str] = None
    occurred_at: datetime

    severity: Optional[EventSeverity] = EventSeverity.medium
    status: Optional[EventStatus] = EventStatus.open

    contractor_id: Optional[str] = None

    # -------------------------------------------------
    # FIX: Parse RFC3339 timestamps w/ trailing Z
    # -------------------------------------------------
    @validator("occurred_at", pre=True)
    def parse_occurred_at(cls, v):
        if isinstance(v, str):
            # Convert "2025-11-18T03:37:20.464Z" → "+00:00"
            if v.endswith("Z"):
                v = v.replace("Z", "+00:00")
        return v


# -------------------------------------------------
# Create Event
# -------------------------------------------------
class EventCreate(EventBase):
    """
    - Client sends this when creating an event.
    - Supabase generates id & created_at
    - created_by is injected by backend
    """
    pass


# -------------------------------------------------
# Read Event
# -------------------------------------------------
class EventRead(EventBase):
    id: str
    created_at: datetime
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

    severity: Optional[EventSeverity] = None
    status: Optional[EventStatus] = None
    contractor_id: Optional[str] = None

    @validator("occurred_at", pre=True)
    def parse_update_occurred_at(cls, v):
        if isinstance(v, str) and v.endswith("Z"):
            return v.replace("Z", "+00:00")
        return v
