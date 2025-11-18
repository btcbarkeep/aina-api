from datetime import datetime
from typing import Optional
from uuid import UUID
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

    # FIX: UUID type instead of str
    contractor_id: Optional[UUID] = None

    # -------------------------------------------------
    # FIX: parse timestamps with trailing Z
    # -------------------------------------------------
    @validator("occurred_at", pre=True)
    def parse_occurred_at(cls, v):
        if isinstance(v, str) and v.endswith("Z"):
            return v.replace("Z", "+00:00")
        return v

    # -------------------------------------------------
    # FIX: auto-null invalid contractor_id
    # -------------------------------------------------
    @validator("contractor_id", pre=True)
    def validate_contractor_id(cls, v):
        if not v:
            return None
        if isinstance(v, UUID):
            return v
        try:
            return UUID(v)
        except Exception:
            # invalid UUID → silently become None
            return None


# -------------------------------------------------
# Create Event
# -------------------------------------------------
class EventCreate(EventBase):
    """
    - Client sends this when creating an event.
    - Supabase generates id & created_at
    - created_by is set by backend
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

    # FIX here also — use UUID type
    contractor_id: Optional[UUID] = None

    @validator("occurred_at", pre=True)
    def parse_update_occurred_at(cls, v):
        if isinstance(v, str) and v.endswith("Z"):
            return v.replace("Z", "+00:00")
        return v

    @validator("contractor_id", pre=True)
    def validate_update_contractor_id(cls, v):
        if not v:
            return None
        if isinstance(v, UUID):
            return v
        try:
            return UUID(v)
        except Exception:
            return None
