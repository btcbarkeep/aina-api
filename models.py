# models.py
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlmodel import SQLModel, Field, UniqueConstraint


# =====================================================
# 🔧 ENUMS
# =====================================================

class EventType(str, Enum):
    maintenance = "maintenance"
    notice = "notice"
    assessment = "assessment"
    plumbing = "plumbing"
    electrical = "electrical"
    general = "general"


# =====================================================
# 🏢 BUILDING MODELS
# =====================================================

class BuildingBase(SQLModel):
    """Shared building fields used across models."""
    name: str = Field(index=True)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


class Building(BuildingBase, table=True):
    """Database table model for buildings."""
    __tablename__ = "buildings"
    __table_args__ = (UniqueConstraint("name", name="uq_building_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class BuildingCreate(BuildingBase):
    """Fields allowed when creating a building."""
    pass


class BuildingRead(BuildingBase):
    """Fields returned when reading a building."""
    id: int
    created_at: datetime


# =====================================================
# 📅 EVENT MODELS
# =====================================================

class EventBase(SQLModel):
    """Shared event fields."""
    building_id: int = Field(foreign_key="buildings.id", index=True)
    unit_number: Optional[str] = Field(default=None, index=True)
    event_type: EventType
    title: str
    body: Optional[str] = None
    occurred_at: datetime


class Event(EventBase, table=True):
    """Database table for events."""
    __tablename__ = "events"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class EventCreate(EventBase):
    """Fields required when creating an event."""
    pass


class EventRead(EventBase):
    """Fields returned when reading an event."""
    id: int
    created_at: datetime


# =====================================================
# 📄 DOCUMENT MODELS
# =====================================================

class DocumentBase(SQLModel):
    event_id: int = Field(foreign_key="events.id", index=True)
    s3_key: str
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None


class Document(DocumentBase, table=True):
    __tablename__ = "documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class DocumentCreate(DocumentBase):
    pass


class DocumentRead(DocumentBase):
    id: int
    created_at: datetime


# =====================================================
# 👤 USER ACCESS MODEL
# =====================================================

class UserBuildingAccess(SQLModel, table=True):
    __tablename__ = "user_building_access"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    building_id: int = Field(foreign_key="buildings.id", index=True)
    role: str = Field(default="hoa", description="hoa, manager, contractor")


# =====================================================
# 🔐 AUTH MODELS
# =====================================================

class LoginRequest(SQLModel):
    username: str
    password: str


class TokenResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"
