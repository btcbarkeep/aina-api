# models/building.py
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, UniqueConstraint

class BuildingBase(SQLModel):
    name: str = Field(index=True)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None

class Building(BuildingBase, table=True):
    __tablename__ = "buildings"
    __table_args__ = (UniqueConstraint("name", name="uq_building_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class BuildingCreate(BuildingBase):
    pass

class BuildingRead(BuildingBase):
    id: int
    created_at: datetime

class BuildingUpdate(SQLModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
