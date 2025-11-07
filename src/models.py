from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


# =====================================================
# BUILDINGS
# =====================================================
class BuildingBase(SQLModel):
    name: str = Field(index=True)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


class Building(BuildingBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class BuildingCreate(SQLModel):
    """Fields allowed when creating a building"""
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


class BuildingRead(BuildingBase):
    """Fields returned when reading a building"""
    id: int
    created_at: datetime


# =====================================================
# EVENTS
# =====================================================
class EventBase(SQLModel):
    building_id: int = Field(foreign_key="building.id", index=True)
    unit_number: Optional[str] = None
    event_type: str = Field(description="e.g., 'assessment', 'notice', 'repair', 'insurance'")
    title: str
    body: Optional[str] = None
    occurred_at: datetime


class Event(EventBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class EventCreate(SQLModel):
    """Fields allowed when creating an event"""
    building_id: int
    unit_number: Optional[str] = None
    event_type: str
    title: str
    body: Optional[str] = None
    occurred_at: datetime


class EventRead(EventBase):
    """Fields returned when reading an event"""
    id: int
    created_at: datetime


# -----------------------------------------------------
#  DOCUMENT MODELS
# -----------------------------------------------------
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel

class DocumentBase(SQLModel):
    event_id: int = Field(foreign_key="event.id", index=True)
    s3_key: str = Field(description="S3 object key, e.g., uploads/uuid.pdf")
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

class Document(DocumentBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class DocumentCreate(SQLModel):
    event_id: int
    s3_key: str
    filename: str

class DocumentRead(DocumentBase):
    id: int
    created_at: datetime
