# models/event.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from .enums import EventType


# -------------------------------------------------
# Shared Fields (used across Create/Read/Update)
# -------------------------------------------------
class EventBase(BaseModel):
    building_id: str                     # UUID from Supabase
    unit_number: Optional[str] = None
    event_type: EventType
    title: str
    body: Optional[str] = None
    occurred_at: datetime


# -------------------------------------------------
# Create Event
# -------------------------------------------------
class EventCreate(EventBase):
    """
    Sent by the client when creating an event.
    No ID or created_at — Supabase generates those.
    """
    pass


# -------------------------------------------------
# Read Event (from Supabase)
# -------------------------------------------------
class EventRead(EventBase):
    id: str                               # Supabase UUID
    created_at: datetime                  # Supabase timestamp


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
