# models/building.py

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, validator


# -------------------------------------------------
# Shared fields
# -------------------------------------------------
class BuildingBase(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


# -------------------------------------------------
# Create
# -------------------------------------------------
class BuildingCreate(BuildingBase):
    """
    Used when creating a building in Supabase.
    No ID supplied — Supabase generates UUID.
    """
    pass


# -------------------------------------------------
# Read (Supabase → API response)
# -------------------------------------------------
class BuildingRead(BuildingBase):
    id: str                      # UUID STRING from Supabase
    created_at: datetime         # Supabase timestamp

    # Normalize UUID → str always
    @validator("id", pre=True)
    def normalize_id(cls, v):
        if isinstance(v, UUID):
            return str(v)
        return str(v)

    # Parse trailing Z timestamps
    @validator("created_at", pre=True)
    def normalize_created_at(cls, v):
        if isinstance(v, str) and v.endswith("Z"):
            return v.replace("Z", "+00:00")
        return v


# -------------------------------------------------
# Update (PATCH)
# -------------------------------------------------
class BuildingUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
