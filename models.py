from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel

class BuildingBase(SQLModel):
    name: str = Field(index=True)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None

class Building(BuildingBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class BuildingCreate(BuildingBase):
    pass

class BuildingRead(BuildingBase):
    id: int
    created_at: datetime

class EventBase(SQLModel):
    building_id: int = Field(foreign_key="building.id", index=True)
    unit_number: Optional[str] = Field(default=None, index=True)
    event_type: str = Field(description="e.g., 'assessment', 'notice', 'repair', 'insurance'")
    title: str
    body: Optional[str] = None
    occurred_at: datetime

class Event(EventBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class EventCreate(EventBase):
    pass

class EventRead(EventBase):
    id: int
    created_at: datetime

class DocumentBase(SQLModel):
    event_id: int = Field(foreign_key="event.id", index=True)
    s3_key: str = Field(description="S3 object key, e.g., uploads/uuid.pdf")
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

class Document(DocumentBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class DocumentCreate(DocumentBase):
    pass

class DocumentRead(DocumentBase):
    id: int
    created_at: datetime
