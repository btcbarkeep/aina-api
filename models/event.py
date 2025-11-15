# models/event.py
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field

from .enums import EventType

class EventBase(SQLModel):
    building_id: int = Field(foreign_key="buildings.id", index=True)
    unit_number: Optional[str] = Field(default=None, index=True)
    event_type: EventType
    title: str
    body: Optional[str] = None
    occurred_at: datetime

class Event(EventBase, table=True):
    __tablename__ = "events"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class EventCreate(EventBase):
    pass

class EventRead(EventBase):
    id: int
    created_at: datetime

class EventUpdate(SQLModel):
    building_id: Optional[int] = None
    unit_number: Optional[str] = None
    event_type: Optional[EventType] = None
    title: Optional[str] = None
    body: Optional[str] = None
    occurred_at: Optional[datetime] = None
