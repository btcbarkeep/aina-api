from typing import Optional
from pydantic import BaseModel, field_validator
from datetime import datetime
from uuid import UUID


# -------------------------------------------------------------------
# UUID Normalization Helper
# Supabase often sends UUID objects OR strings → we normalize both.
# -------------------------------------------------------------------
def _normalize_uuid(value):
    if not value:
        return None
    if isinstance(value, UUID):
        return str(value)
    try:
        return str(UUID(str(value)))
    except Exception:
        return None


# -------------------------------------------------------------------
# BASE MODEL (shared fields)
# -------------------------------------------------------------------
class EventCommentBase(BaseModel):
    event_id: str                    # ALWAYS string-safe for Supabase
    user_id: Optional[str] = None    # Filled by router
    comment_text: str

    @field_validator("event_id", "user_id", mode="before")
    def normalize_uuid_fields(cls, v):
        return _normalize_uuid(v)


# -------------------------------------------------------------------
# CREATE MODEL (incoming from client)
# -------------------------------------------------------------------
class EventCommentCreate(BaseModel):
    event_id: str
    comment_text: str

    @field_validator("event_id", mode="before")
    def validate_event_id(cls, v):
        value = _normalize_uuid(v)
        if not value:
            raise ValueError("Invalid event_id UUID")
        return value


# -------------------------------------------------------------------
# UPDATE MODEL (partial update)
# -------------------------------------------------------------------
class EventCommentUpdate(BaseModel):
    comment_text: Optional[str] = None


# -------------------------------------------------------------------
# READ MODEL (Supabase → API response)
# -------------------------------------------------------------------
class EventCommentRead(EventCommentBase):
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("id", mode="before")
    def normalize_id(cls, v):
        return _normalize_uuid(v)

    @field_validator("created_at", "updated_at", mode="before")
    def normalize_timestamps(cls, v):
        if isinstance(v, str) and v.endswith("Z"):
            return v.replace("Z", "+00:00")
        return v
