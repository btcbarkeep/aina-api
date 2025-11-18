from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, field_validator

from .enums import EventType, EventSeverity, EventStatus


# -------------------------------------------------
# Shared Fields (Supabase-safe)
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

    # Supabase returns UUID as string → enforce string always
    contractor_id: Optional[str] = None

    # -------------------------------------------------
    # Normalize timestamps like "2025-01-01T00:00:00Z"
    # -------------------------------------------------
    @field_validator("occurred_at", mode="before")
    def parse_occurred_at(cls, v):
        if isinstance(v, str) and v.endswith("Z"):
            return v.replace("Z", "+00:00")
        return v

    # -------------------------------------------------
    # Normalize contractor_id (UUID → string)
    # -------------------------------------------------
    @field_validator("contractor_id", mode="before")
    def validate_contractor_id(cls, v):
        if not v:
            return None

        # UUID object → convert to string
        if isinstance(v, UUID):
            return str(v)

        # String that might be UUID → validate & return
        try:
            return str(UUID(str(v)))
        except Exception:
            # Invalid UUID safely becomes None
            return None


# -------------------------------------------------
# Create Event
# -------------------------------------------------
class EventCreate(EventBase):
    """
    Client sends this when creating an event.
    Supabase auto-generates id & created_at.
    Backend sets created_by.
    """
    pass


# -------------------------------------------------
# Read Event (ALWAYS STRING SAFE)
# -------------------------------------------------
class EventRead(EventBase):
    id: str
    created_at: datetime
    created_by: Optional[str] = None

    @field_validator("id", mode="before")
    def id_to_str(cls, v):
        return str(v)


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

    @field_validator("occurred_at", mode="before")
    def parse_update_occurred_at(cls, v):
        if isinstance(v, str) and v.endswith("Z"):
            return v.replace("Z", "+00:00")
        return v

    @field_validator("contractor_id", mode="before")
    def validate_update_contractor_id(cls, v):
        if not v:
            return None
        if isinstance(v, UUID):
            return str(v)
        try:
            return str(UUID(str(v)))
        except Exception:
            return None
