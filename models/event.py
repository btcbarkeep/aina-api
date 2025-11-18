from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, validator

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

    # ❗ Supabase-safe string, NOT UUID object
    contractor_id: Optional[str] = None

    # -------------------------------------------------
    # Normalize timestamps with trailing Z
    # -------------------------------------------------
    @validator("occurred_at", pre=True)
    def parse_occurred_at(cls, v):
        if isinstance(v, str) and v.endswith("Z"):
            return v.replace("Z", "+00:00")
        return v

    # -------------------------------------------------
    # Validate contractor_id (accept UUID or string)
    # Always store internally as a string
    # -------------------------------------------------
    @validator("contractor_id", pre=True)
    def validate_contractor_id(cls, v):
        if not v:
            return None

        # If UUID object → convert to string
        if isinstance(v, UUID):
            return str(v)

        # Try converting string → UUID → back to str
        try:
            return str(UUID(str(v)))
        except Exception:
            # invalid UUID → silently null
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

    # Must also be string-safe
    contractor_id: Optional[str] = None

    @validator("occurred_at", pre=True)
    def parse_update_occurred_at(cls, v):
        if isinstance(v, str) and v.endswith("Z"):
            return v.replace("Z", "+00:00")
        return v

    # Same UUID normalization as EventBase
    @validator("contractor_id", pre=True)
    def validate_update_contractor_id(cls, v):
        if not v:
            return None
        if isinstance(v, UUID):
            return str(v)
        try:
            return str(UUID(str(v)))
        except Exception:
            return None
