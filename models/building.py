# models/building.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


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


# -------------------------------------------------
# Update (PATCH)
# -------------------------------------------------
class BuildingUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
