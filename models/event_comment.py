from typing import Optional
from pydantic import BaseModel
from datetime import datetime


# -----------------------------------------
# BASE MODEL (fields shared across models)
# -----------------------------------------
class EventCommentBase(BaseModel):
    event_id: str
    user_id: Optional[str]  # Filled automatically from JWT
    comment_text: str


# -----------------------------------------
# CREATE MODEL
# -----------------------------------------
class EventCommentCreate(BaseModel):
    event_id: str          # UUID of parent event
    comment_text: str      # Actual comment text


# -----------------------------------------
# UPDATE MODEL
# -----------------------------------------
class EventCommentUpdate(BaseModel):
    comment_text: Optional[str] = None


# -----------------------------------------
# READ / RETURN MODEL
# -----------------------------------------
class EventCommentRead(EventCommentBase):
    id: str                    # UUID primary key
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
