from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, field_validator, Field

from .enums import EventType, EventSeverity, EventStatus


# -------------------------------------------------
# Shared Fields (Supabase-safe)
# -------------------------------------------------
class EventBase(BaseModel):
    building_id: str

    # Legacy single unit_id (for backward compatibility)
    # If unit_ids is provided, this is ignored
    unit_id: Optional[str] = None

    # NEW — Multiple units support
    unit_ids: Optional[List[str]] = Field(None, description="List of unit IDs associated with this event")

    event_type: EventType
    title: str
    body: Optional[str] = None
    occurred_at: datetime

    severity: Optional[EventSeverity] = EventSeverity.medium
    status: Optional[EventStatus] = EventStatus.open

    # Legacy single contractor_id (for backward compatibility)
    # If contractor_ids is provided, this is ignored
    contractor_id: Optional[str] = None

    # NEW — Multiple contractors support
    contractor_ids: Optional[List[str]] = Field(None, description="List of contractor IDs associated with this event")

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
        if isinstance(v, UUID):
            return str(v)
        try:
            return str(UUID(str(v)))
        except Exception:
            return None

    # -------------------------------------------------
    # Normalize unit_id (UUID → string, or None)
    # -------------------------------------------------
    @field_validator("unit_id", mode="before")
    def validate_unit_id(cls, v):
        if not v:
            return None
        if isinstance(v, UUID):
            return str(v)
        try:
            return str(UUID(str(v)))
        except Exception:
            return None

    # -------------------------------------------------
    # Normalize unit_ids (List of UUIDs → List of strings)
    # -------------------------------------------------
    @field_validator("unit_ids", mode="before")
    def validate_unit_ids(cls, v):
        if not v:
            return None
        if not isinstance(v, list):
            return None
        result = []
        for item in v:
            if not item:
                continue
            if isinstance(item, UUID):
                result.append(str(item))
            else:
                try:
                    result.append(str(UUID(str(item))))
                except Exception:
                    continue
        return result if result else None

    # -------------------------------------------------
    # Normalize contractor_ids (List of UUIDs → List of strings)
    # -------------------------------------------------
    @field_validator("contractor_ids", mode="before")
    def validate_contractor_ids(cls, v):
        if not v:
            return None
        if not isinstance(v, list):
            return None
        result = []
        for item in v:
            if not item:
                continue
            if isinstance(item, UUID):
                result.append(str(item))
            else:
                try:
                    result.append(str(UUID(str(item))))
                except Exception:
                    continue
        return result if result else None


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
    unit_id: Optional[str] = None
    unit_ids: Optional[List[str]] = Field(None, description="List of unit IDs associated with this event")

    event_type: Optional[EventType] = None
    title: Optional[str] = None
    body: Optional[str] = None
    occurred_at: Optional[datetime] = None

    severity: Optional[EventSeverity] = None
    status: Optional[EventStatus] = None

    contractor_id: Optional[str] = None
    contractor_ids: Optional[List[str]] = Field(None, description="List of contractor IDs associated with this event")

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

    @field_validator("unit_id", mode="before")
    def validate_update_unit_id(cls, v):
        if not v:
            return None
        if isinstance(v, UUID):
            return str(v)
        try:
            return str(UUID(str(v)))
        except Exception:
            return None

    @field_validator("unit_ids", mode="before")
    def validate_update_unit_ids(cls, v):
        if not v:
            return None
        if not isinstance(v, list):
            return None
        result = []
        for item in v:
            if not item:
                continue
            if isinstance(item, UUID):
                result.append(str(item))
            else:
                try:
                    result.append(str(UUID(str(item))))
                except Exception:
                    continue
        return result if result else None

    @field_validator("contractor_ids", mode="before")
    def validate_update_contractor_ids(cls, v):
        if not v:
            return None
        if not isinstance(v, list):
            return None
        result = []
        for item in v:
            if not item:
                continue
            if isinstance(item, UUID):
                result.append(str(item))
            else:
                try:
                    result.append(str(UUID(str(item))))
                except Exception:
                    continue
        return result if result else None
