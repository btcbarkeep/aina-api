from typing import Optional
from pydantic import BaseModel
from datetime import datetime


# -----------------------------------------
# BASE MODEL (shared fields)
# -----------------------------------------
class EventCommentBase(BaseModel):
    event_id: str                  # Supabase UUID
    user_id: Optional[str] = None  # Filled automatically from JWT in the router
    comment_text: str


# -----------------------------------------
# CREATE MODEL
# -----------------------------------------
class EventCommentCreate(BaseModel):
    event_id: str                  # UUID of parent event
    comment_text: str              # Actual comment text


# -----------------------------------------
# UPDATE MODEL (partial)
# -----------------------------------------
class EventCommentUpdate(BaseModel):
    comment_text: Optional[str] = None


# -----------------------------------------
# READ MODEL (returned from Supabase)
# -----------------------------------------
class EventCommentRead(EventCommentBase):
    id: str                        # UUID primary key
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
