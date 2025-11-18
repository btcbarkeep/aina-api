# models/event_comment.py

from typing import Optional
from pydantic import BaseModel, validator
from datetime import datetime
from uuid import UUID


# -------------------------------------------------------------------
# BASE MODEL (shared fields)
# -------------------------------------------------------------------
class EventCommentBase(BaseModel):
    event_id: UUID                  # Supabase UUID
    user_id: Optional[UUID] = None  # Filled automatically by router
    comment_text: str

    # Normalize UUID inputs (strings → UUID objects)
    @validator("event_id", "user_id", pre=True)
    def parse_uuid(cls, v):
        if not v:
            return None
        if isinstance(v, UUID):
            return v
        try:
            return UUID(str(v))
        except Exception:
            return None


# -------------------------------------------------------------------
# CREATE MODEL (incoming from client)
# -------------------------------------------------------------------
class EventCommentCreate(BaseModel):
    event_id: UUID
    comment_text: str

    @validator("event_id", pre=True)
    def parse_uuid(cls, v):
        if isinstance(v, UUID):
            return v
        try:
            return UUID(str(v))
        except Exception:
            raise ValueError("Invalid event_id UUID")


# -------------------------------------------------------------------
# UPDATE MODEL (partial)
# -------------------------------------------------------------------
class EventCommentUpdate(BaseModel):
    comment_text: Optional[str] = None


# -------------------------------------------------------------------
# READ MODEL (returned from Supabase)
# -------------------------------------------------------------------
class EventCommentRead(EventCommentBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
